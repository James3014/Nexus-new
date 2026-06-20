# S1: Repro/Env Lane Optimization Plan

**目標**: 把 5 題 smoke 中 3 題的 `DEPENDENCY_MISMATCH` 降到可處理範圍
**策略**: 先修 Nexus 能力，再擴題量
**狀態**: 待執行

---

## Failure 分析（from 5-task smoke rerun）

| Task | Stop Layer | Failure Class | 語義 |
|------|-----------|---------------|------|
| sympy__sympy-12489 | repro_runner | DEPENDENCY_MISMATCH | sympy 依賴版本不對 |
| psf__requests-2317 | repro_runner | DEPENDENCY_MISMATCH | requests 依賴版本不對 |
| matplotlib__matplotlib-23299 | repro_runner | REPRO_NOT_REPRODUCED | bug 重現失敗 |
| astropy__astropy-14365 | verification | SOLVED | ✅ |
| django__django-11099 | verification | SOLVED | ✅ |

**主瓶頸**: 3/5 在 repro/env lane（DEPENDENCY_MISMATCH × 2 + REPRO_NOT_REPRODUCED × 1）

---

## S1 Tasks

### Task S1-A: EnvRecipeRegistry 實際接入 pipeline

**目標**: 讓 EnvResolver 在 reproduction phase 自動匹配 recipe 並執行
**現狀**: recipe registry 已建立但未接入 pipeline
**做法**:
1. 在 `ReproductionPhase.execute()` 中加入 recipe matching
2. 匹配到 recipe 時自動執行 allowed_actions（僅限 pip install / mock import）
3. 執行後 re-try reproduction
4. 所有 recipe 執行寫入 env receipt telemetry

**TDD**:
- Red: 寫 fixture test，給 sympy DEPENDENCY_MISMATCH signal，期待 recipe 匹配並產生 action plan
- Green: 最小實作 recipe matching + action execution
- Refactor: 把 execution 從 phase 中抽出成獨立 function

**驗收**: 給定 DEPENDENCY_MISMATCH signal，pipeline 自動嘗試 recipe fix

### Task S1-B: Repro pre-flight gate 接入 pipeline

**目標**: 在 patch synthesis 之前加 formal pre-flight gate
**做法**:
1. 在 `HealOrchestrator.run()` 的 patch phase 前插入 `ReproPreflightDiagnosis.diagnose(ctx)`
2. `can_enter_patch_lane=False` 時停在 reprorunner
3. gate 結果寫入 receipt

**TDD**:
- Red: 寫測試，bug 未重現時 pipeline 不進入 patch lane
- Green: 最小實作 gate
- Refactor: 整合到 orchestrator flow

**驗收**: bug 未重現時 `observed_stop_layer=reprorunner`，不進入 patch lane

### Task S1-C: 環境失敗 → recipe → re-repro 迴圈

**目標**: 建立 env failure → recipe fix → re-repro 的自動迴圈
**做法**:
1. Reproduction 失敗 → 進入 env_resolver
2. EnvResolver 匹配 recipe → 執行 fix
3. Fix 後 re-run reproduction
4. 最多重試 2 次 recipe fix

**TDD**:
- Red: 寫測試，DEPENDENCY_MISMATCH → recipe fix → re-repro 成功
- Green: 最小實作迴圈
- Refactor: 限制重試次數，防止無限迴圈

**驗收**: sympy/requests 類的 DEPENDENCY_MISMATCH 有機會被自動修復

---

## S2: Re-smoke（5 題）

完成 S1 後，重跑原 5 題，驗證：
- DEPENDENCY_MISMATCH 是否減少
- repro_runner stop layer 是否減少
- claim_eligible=true 的題數是否增加

## S3: 中批次（15-20 題）

S2 通過後，從 manifest 中選 15-20 題（覆蓋 sympy/psf/astropy/django/matplotlib），驗證 failure distribution 是否改變。

## S4: 82 題

S3 顯示 failure distribution 有改善後，再開 82 題。
