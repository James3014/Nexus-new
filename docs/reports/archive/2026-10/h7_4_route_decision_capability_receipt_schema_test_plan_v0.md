# H7-4 RouteDecision / CapabilityReceipt Schema Consistency Test Gate Plan v0

**日期**: 2026-06-25  
**狀態**: `H7_4_SCHEMA_CONSISTENCY_TEST_GATE_PLAN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 plan/report-only 產出。本任務期間未新增任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call、未修改任何 production code 或 tests。H7 仍處於 planning-only 階段。

---

## 0. Status / Safety Boundary

* **status**: `H7_4_SCHEMA_CONSISTENCY_TEST_GATE_PLAN_DRAFT_READY_FOR_REVIEW`
* **no runtime behavior change** (不改變執行期行為)
* **no provider call** (不呼叫 provider)
* **no model call** (不進行模型調用)
* **no network call** (不啟用網路)
* **no model load** (不載入模型)
* **no model execution** (不執行模型)
* **no learned policy adoption** (不啟用學習策略)
* **no new router** (不新增路由器)
* **no production code modification** (不修改任何 `nexus/**/*.py`)
* **no test modification** (不修改任何 `tests/**/*.py`)
* **production_ready=false**
* **public_claim_allowed=false**
* **H7 runtime not started** (H7 執行期尚未啟動)

---

## 1. Scope

本 report 根據 H7-3 的 field alignment audit 結果，規劃具體且可執行的 test gate 設計方案。目標是在不修改任何 production code 或現有 tests 的前提下，定義各個 test gate 的：
- 測試目的
- 測試標的模組
- 測試方法（pytest fixture / parametrize / mock 設計）
- 斷言邏輯
- 預期 pass/fail 條件
- 與 H7-2 AutonomicRouter 隔離設計的整合邊界

**H7-4 is plan-only**: 本 report 僅設計測試計畫，不建立任何 test 檔案或程式修改。

---

## 2. Test Gate 總覽

| Gate ID | 測試名稱 | 目標模組 | 核心斷言 | H7 必要? | H8 必要? | recovery blocker? |
|---|---|---|---|---|---|---|
| TG-01 | RouteDecision schema consistency | `capability_contracts.py` | Plan → RouteDecision 型別轉換強型別 | yes | yes | no |
| TG-02 | CapabilityReceipt false assertion | `capability_contracts.py` | invoked=False 時 telemetries 歸零 | yes | yes | no |
| TG-03 | SkillReceipt selected/invoked consistency | `capability_contracts.py` | selected 但未 was_injected 必拋錯 | yes | yes | no |
| TG-04 | public_claim_safe fail-closed | `capability_contracts.py` | telemetries 缺失時回傳 False | yes | yes | no |
| TG-05 | evidence_refs linkage | `capability_contracts.py` | public_claim_safe=true 時 evidence_refs 非空 | yes | yes | no |
| TG-06 | provider/model/network field denial | `capability_contracts.py` / `s2t_policy.py` | provider/network flags 鎖定 False | yes | yes | yes |
| TG-07 | recovery readiness blocker | `capability_contracts.py` / `local_heal/` | hash 缺失時 RECOVERY_UNSAFE | no | yes | yes |
| TG-08 | AutonomicRouter restriction | `autonomic_routing_service.py` | AutonomicRouter 僅讀 signal，不寫 state | yes | yes | no |
| TG-09 | Learning policy override prevention | `s2t_policy.py` / `router_nas_tuner.py` | shadow_only=true 時 adoption_allowed=False | yes | yes | no |

---

## 3. 各 Gate 詳細設計

### TG-01 RouteDecision Schema Consistency Test

**目的**: 驗證 `CapabilityPlanner.settle()` 從 `Plan` (list of SkillRoutes) 轉換成 `RouteDecision` 時，欄位型別完全符合 H7-3 alignment matrix 中的強型別規格。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `RouteDecision`, `CapabilityPlan`

**測試策略**:
```python
# 建議 test 路徑（H7-5 實作時使用）:
# tests/unit/engine/test_route_decision_schema.py

@pytest.mark.parametrize("field,expected_type", [
    ("task_id", str),
    ("selected_skills", list),
    ("fallback_allowed", bool),
    ("public_claim_safe", bool),
    ("evidence_refs", list),
])
def test_route_decision_field_types(field, expected_type):
    receipt = build_minimal_route_decision()
    assert isinstance(getattr(receipt, field), expected_type)
```

**斷言邏輯**:
- `task_id`: 必須是非空 `str`
- `selected_skills`: 必須是 `list`（允許空 list，但不允許 `None`）
- `fallback_allowed`: 必須是 `bool`（不接受 `int` 或 truthy string）
- `public_claim_safe`: 必須是 `bool`，預設值必須是 `False`
- `evidence_refs`: 必須是 `list`（允許空 list）

**Pass 條件**: 所有 parametrize 組合均通過型別斷言。  
**Fail 條件**: 任一欄位型別不符合、`public_claim_safe` 預設為 True、`task_id` 為 None。

**H7-3 依據**: Field Alignment Matrix 第 50 行 `task_id` 與規劃中 `decision_id`、`route_id`。

---

### TG-02 CapabilityReceipt False Assertion Test

**目的**: 驗證當 `invoked=False` 時，`CapabilityReceipt.telemetries` 中所有可計費欄位均強制歸零，防止幽靈計費。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `CapabilityReceipt`

**測試策略**:
```python
# tests/unit/engine/test_capability_receipt_false_assertion.py

def test_receipt_telemetries_zero_when_not_invoked():
    receipt = CapabilityReceipt(
        task_id="test-001",
        invoked=False,
        telemetries={"model_calls": 0, "token_usage": 0, "provider_costs": 0.0}
    )
    assert receipt.telemetries["model_calls"] == 0
    assert receipt.telemetries["token_usage"] == 0
    assert receipt.telemetries["provider_costs"] == 0.0

def test_receipt_rejects_nonzero_telemetries_when_not_invoked():
    with pytest.raises((ValueError, AssertionError)):
        CapabilityReceipt(
            task_id="test-001",
            invoked=False,
            telemetries={"model_calls": 1}  # 應拋錯
        )
```

**斷言邏輯**:
- `invoked=False` → `model_calls == 0`
- `invoked=False` → `token_usage == 0`
- `invoked=False` → `provider_costs == 0.0`
- 若 invoked=False 但 telemetries 含非零值，必須拋出 `ValueError` 或 `AssertionError`

**Pass 條件**: 0 值通過，非零值拋錯。  
**Fail 條件**: invoked=False 但 telemetries 非零仍被接受。

**H7-3 依據**: Field Alignment Matrix `invoked` 欄位與 `public_claim_safe` 強制 False 邏輯。

---

### TG-03 SkillReceipt Selected/Invoked Consistency Test

**目的**: 驗證 `SkillReceipt` 在 `selected=True` 但 `was_injected=False` 的矛盾狀態下，必須拋出 `selected_without_injection` 語義錯誤，防止「幽靈注入」。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `SkillReceipt`

**測試策略**:
```python
# tests/unit/engine/test_skill_receipt_consistency.py

@pytest.mark.parametrize("selected,was_injected,should_raise", [
    (True,  True,  False),   # 正常：selected + injected
    (False, False, False),   # 正常：未 selected + 未 injected
    (True,  False, True),    # 錯誤：selected 但未 injected → 必須拋錯
    (False, True,  False),   # 允許（未 selected 但曾 injected，edge case）
])
def test_skill_receipt_selected_injected_consistency(selected, was_injected, should_raise):
    if should_raise:
        with pytest.raises((ValueError, AssertionError)):
            SkillReceipt(skill_name="test", selected=selected, was_injected=was_injected)
    else:
        receipt = SkillReceipt(skill_name="test", selected=selected, was_injected=was_injected)
        assert receipt.selected == selected
```

**Pass 條件**: 矛盾狀態拋錯，正常狀態通過。  
**Fail 條件**: selected=True + was_injected=False 被靜默接受。

**H7-3 依據**: Recommended Test Gates 第 3 條。

---

### TG-04 public_claim_safe Fail-Closed Test

**目的**: 驗證當 `telemetries` 丟失、為 `None`、含 `estimated` 或 `unknown` 標記時，`public_claim_safe` 必須強制回傳 `False`，不得預設為 True。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `CapabilityReceipt`

**測試策略**:
```python
# tests/unit/engine/test_public_claim_safe.py

@pytest.mark.parametrize("telemetries,expected", [
    (None,                              False),  # telemetries 丟失
    ({},                                False),  # telemetries 空
    ({"model_calls": "estimated"},      False),  # estimated 標記
    ({"token_usage": "unknown"},        False),  # unknown 標記
    ({"model_calls": 0, "token_usage": 0, "provider_costs": 0.0}, True),  # 清晰零值
])
def test_public_claim_safe_fail_closed(telemetries, expected):
    receipt = build_receipt_with_telemetries(telemetries)
    assert receipt.public_claim_safe == expected
```

**斷言邏輯**:
- `public_claim_safe` 是計算屬性（property），必須 fail-closed
- 任何 `estimated`/`unknown`/`None` → `False`
- 僅當所有 telemetry 欄位均為確定零值時允許 `True`（且需配合 TG-05 的 evidence_refs 檢查）

**Pass 條件**: 不確定性一律 False，確定零值允許 True。  
**Fail 條件**: telemetries=None 但 public_claim_safe 仍回傳 True。

**H7-3 依據**: Alignment Decision 第 2 條、Recommended Test Gates 第 4 條。

---

### TG-05 evidence_refs Linkage Test

**目的**: 驗證當 `public_claim_safe=True` 時，`evidence_refs` 不得為空 list，必須包含至少一筆 verifier 憑據連結；反之 `public_claim_safe=False` 時允許空 `evidence_refs`。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `CapabilityReceipt` / `RouteDecision`

**測試策略**:
```python
# tests/unit/engine/test_evidence_refs_linkage.py

def test_evidence_refs_required_when_public_claim_safe():
    with pytest.raises((ValueError, AssertionError)):
        receipt = CapabilityReceipt(
            task_id="test-001",
            invoked=True,
            public_claim_safe=True,
            evidence_refs=[],  # 應拋錯：公開宣告必須有 evidence
        )

def test_evidence_refs_optional_when_not_public_claim_safe():
    receipt = CapabilityReceipt(
        task_id="test-001",
        invoked=False,
        public_claim_safe=False,
        evidence_refs=[],  # 應允許：非公開宣告不強制 evidence
    )
    assert receipt.evidence_refs == []
```

**Pass 條件**: public_claim_safe=True + evidence_refs=[] 拋錯；public_claim_safe=False + evidence_refs=[] 允許。  
**Fail 條件**: 允許無 evidence 的公開宣告。

**H7-3 依據**: Recommended Test Gates 第 5 條。

---

### TG-06 Provider / Model / Network Field Denial Test

**目的**: 驗證所有與 provider、model-load、network 相關的 feature flags 在 H7 期間均強制為 `False`，無法被任何路徑覆寫。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `CapabilityPlan`, `CapabilityReceipt`
- `nexus/contracts/s2t_policy.py` — `S2TPolicy`

**測試策略**:
```python
# tests/unit/engine/test_provider_denial_fields.py

DENIAL_FIELDS = [
    "model_call_executed",
    "provider_invoked",
    "network_accessed",
    "model_loaded",
]

@pytest.mark.parametrize("field", DENIAL_FIELDS)
def test_denial_field_must_be_false_by_default(field):
    receipt = build_minimal_capability_receipt()
    val = getattr(receipt, field, None)
    # field 可能不存在（missing_or_moved），但若存在必須為 False
    if val is not None:
        assert val is False, f"Expected {field}=False, got {val}"

def test_s2t_policy_runtime_effect_is_false():
    from nexus.contracts.s2t_policy import S2TPolicy
    policy = S2TPolicy.load_default()
    assert policy.runtime_effect is False
```

**斷言邏輯**:
- 若欄位存在：必須 `== False`
- 若欄位 `missing_or_moved`：記錄為 `MISSING_CONFIRMED` 但不 fail（H8 需新增）
- `S2TPolicy.runtime_effect` 必須是 `False`

**Pass 條件**: 所有存在欄位均為 False；missing 欄位記錄不 fail。  
**Fail 條件**: 任一 denial field 為 True 或 truthy。

**H7-3 依據**: Alignment Decision `runtime_effect=False`、Recommended Test Gates 第 7 條。

---

### TG-07 Recovery Readiness Blocker Test

**目的**: 驗證當 `selected_candidate_hash` 或 `applied_patch_hash` 缺失時，系統必須回傳 `RECOVERY_UNSAFE` 並禁止自癒程序啟動，防止 blind resume。

**目標模組**:
- `nexus/engine/capability_contracts.py` — `RouteDecision` (規劃中欄位)
- `nexus/services/local_heal/` — recovery readiness gate

**測試策略**:
```python
# tests/unit/engine/test_recovery_readiness_blocker.py

REQUIRED_RECOVERY_FIELDS = [
    "selected_candidate_hash",
    "applied_patch_hash",
]

@pytest.mark.parametrize("missing_field", REQUIRED_RECOVERY_FIELDS)
def test_recovery_blocked_when_hash_missing(missing_field):
    """當關鍵 hash 欄位缺失時，recovery gate 必須回傳 RECOVERY_UNSAFE"""
    state = build_recovery_state_without(missing_field)
    result = check_recovery_readiness(state)
    assert result.status == "RECOVERY_UNSAFE"
    assert result.blocking_reason is not None

def test_recovery_allowed_when_hashes_present():
    """當兩個 hash 均存在時，recovery gate 可通過（但仍須 H8 完整驗證）"""
    state = build_recovery_state_with_hashes(
        selected_candidate_hash="abc123",
        applied_patch_hash="def456",
    )
    result = check_recovery_readiness(state)
    assert result.status != "RECOVERY_UNSAFE"
```

**斷言邏輯**:
- 缺少 `selected_candidate_hash` → `RECOVERY_UNSAFE`
- 缺少 `applied_patch_hash` → `RECOVERY_UNSAFE`
- `phase_pointer` 缺失時補充警告，但不立即 block（視 H8 決策）
- 兩個 hash 均存在 → 允許 recovery gate 通過

**Pass 條件**: 缺 hash 時正確回傳 RECOVERY_UNSAFE；完整 hash 時通過。  
**Fail 條件**: 缺 hash 時允許 recovery 繼續執行。

**H7-3 依據**: U3 Blockers 第 2、3 條；Recovery Projection 審計結論。

> **注意**: 此 gate 在 H7 期間為 plan-only。`selected_candidate_hash` 與 `applied_patch_hash` 尚未在 contracts 中定義，故 H7-5 實作時須先確認 contracts 新增這兩個欄位後再建立 test。

---

### TG-08 AutonomicRouter Restriction Test

**目的**: 驗證 `AutonomicRouter` 僅能以唯讀方式接收 `AutonomicSignal`，不得直接寫入或改變 `state.metadata`，確保 H7-2 隔離設計正確執行。

**目標模組**:
- `nexus/engine/autonomic_routing_service.py` — `AutonomicRoutingService`

**測試策略**:
```python
# tests/unit/engine/test_autonomic_router_restriction.py

def test_autonomic_router_does_not_mutate_state_metadata():
    """AutonomicRouter 信號處理不得寫入 state.metadata"""
    from unittest.mock import MagicMock, patch
    
    state = MagicMock()
    state.metadata = {"original_key": "original_value"}
    original_metadata = dict(state.metadata)
    
    signal = AutonomicSignal(
        task_id="test-001",
        suggested_mode="PARALLEL",
        confidence=0.85,
    )
    
    service = AutonomicRoutingService()
    service.process_signal(signal, state)  # 應只讀 signal，不改 state
    
    # state.metadata 不得被修改
    assert state.metadata == original_metadata

def test_autonomic_signal_is_readonly_input_only():
    """AutonomicSignal 必須是 frozen dataclass 或 immutable"""
    signal = AutonomicSignal(task_id="test-001", suggested_mode="PARALLEL", confidence=0.9)
    with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
        signal.suggested_mode = "SEQUENTIAL"  # 不得可改動
```

**斷言邏輯**:
- `state.metadata` 在 `process_signal` 前後必須完全相同
- `AutonomicSignal` 必須是 immutable（frozen dataclass）
- `AutonomicRoutingService` 不得直接呼叫 `state.metadata.__setitem__`

**Pass 條件**: state.metadata 未被修改；signal immutability 確認。  
**Fail 條件**: 任何 metadata 寫入操作被偵測到。

**H7-3 依據**: H7-2 隔離設計；AutonomicRouter 直接 mutation 問題（`autonomic_routing_service.py`）。

---

### TG-09 Learning Policy Override Prevention Test

**目的**: 驗證 `S2TPolicy` 在 `shadow_only=true` 狀態下，`adoption_allowed` 必須強制鎖定為 `False`，`router_nas_tuner` 不得觸發 runtime threshold 更新。

**目標模組**:
- `nexus/contracts/s2t_policy.py` — `S2TPolicy`
- `nexus/learning/router_nas_tuner.py` — `RouterNasTuner`

**測試策略**:
```python
# tests/unit/learning/test_learning_policy_override_prevention.py

def test_s2t_shadow_only_blocks_adoption():
    """shadow_only=True 時，adoption_allowed 必須為 False"""
    policy = S2TPolicy(shadow_only="shadow_only")
    assert policy.adoption_allowed is False

def test_router_nas_tuner_does_not_update_router_when_shadow():
    """shadow 模式下，NAS tuner 不得對 router 進行 threshold 更新"""
    from unittest.mock import MagicMock, patch
    
    router = MagicMock()
    tuner = RouterNasTuner(policy=S2TPolicy(shadow_only="shadow_only"))
    
    tuner.tune(router, signal=build_nas_signal())
    
    # 在 shadow 模式下，router 的 update 方法不得被呼叫
    router.update_threshold.assert_not_called()
    router.set_mode.assert_not_called()

def test_runtime_effect_cannot_be_enabled_in_h7():
    """H7 期間，runtime_effect 不得從 False 變為 True"""
    policy = S2TPolicy.load_default()
    assert policy.runtime_effect is False
    
    # 嘗試提升為 runtime — 應拋錯或被攔截
    with pytest.raises((ValueError, PermissionError, AssertionError)):
        policy.promote_to_runtime()
```

**斷言邏輯**:
- `shadow_only=True` → `adoption_allowed == False`
- `RouterNasTuner.tune()` 在 shadow 模式下不得呼叫 `router.update_threshold()`
- `S2TPolicy.runtime_effect` 在 H7 期間不得被設為 True

**Pass 條件**: shadow 模式完全隔離，router 未被更新。  
**Fail 條件**: shadow 模式下 router 被觸發 threshold 更新。

**H7-3 依據**: Alignment Decision 第 4、5 條；Recommended Test Gates 第 8、9 條。

---

## 4. Test Implementation Sequencing（H7-5 以後）

本計畫規定以下實作順序（H7-5 執行時遵守）：

1. **TG-06 先行**（provider denial fields）：最高優先，確保 H7 期間 provider 邊界鎖死不可被 test 本身繞過。
2. **TG-04 + TG-05**（public_claim_safe fail-closed + evidence_refs）：第二優先，直接保護公開宣告安全邊界。
3. **TG-01 + TG-02 + TG-03**（schema consistency + false assertion + SkillReceipt）：第三，核心 schema integrity。
4. **TG-08 + TG-09**（AutonomicRouter restriction + learning policy）：第四，routing 隔離邊界。
5. **TG-07**（recovery readiness blocker）：最後，依賴 H8 的 selected_candidate_hash 欄位定義，H7-5 僅做 skeleton。

---

## 5. Mock / Fixture Design Principles

H7-5 實作時須遵守以下 fixture 設計原則：

1. **所有 fixtures 必須使用 in-process mock**：不得啟動任何 subprocess、provider、model-load 或 network socket。
2. **Build helpers 必須是 pure function**：`build_minimal_route_decision()`、`build_recovery_state_without()` 等必須是無副作用的工廠函數。
3. **No live network**：所有測試必須加 `@pytest.mark.no_network` 或等效 marker。
4. **No model call**：所有測試完成後 `model_calls` telemetry 必須為 0。
5. **Parametrize over enumerate**：優先用 `@pytest.mark.parametrize` 取代手動 loop，提升 test reporter 可讀性。

---

## 6. Acceptance Criteria

* `docs/reports/h7_4_route_decision_capability_receipt_schema_test_plan_v0.md` 檔案確實存在。
* 本 report 為純 plan，未修改任何 production code（`nexus/**/*.py` 均未修改）。
* 未修改任何 tests（`tests/**/*.py` 均未修改）。
* 未執行任何 provider / model / network / model-load / model-call。
* 未新增任何路由器。
* 未變更執行期選路行為。
* 未啟用 learned policy。
* 未混入任何 unrelated dirty files。
* 最終狀態字串為：`H7_4_SCHEMA_CONSISTENCY_TEST_GATE_PLAN_DRAFT_READY_FOR_REVIEW`。

---

## 7. Recommended Next Task

### H7-5 Schema Consistency Test Gate Implementation

* **原因**: H7-4 已規劃 9 個 test gate 的完整設計，包含 module 目標、fixture 策略、斷言邏輯與實作優先順序。H7-5 應依照本計畫，從 TG-06（provider denial fields）開始，逐步建立 `tests/unit/engine/` 下的測試檔案，每個 gate 均以 TDD red-green 方式確認。
* **前置條件**:
  - H7-4 plan 已 commit
  - `capability_contracts.py` schema 審計（H7-3）已接受
  - Provider boundary deny-by-default 仍有效

---

## 8. Final State

`H7_4_SCHEMA_CONSISTENCY_TEST_GATE_PLAN_DRAFT_READY_FOR_REVIEW`
