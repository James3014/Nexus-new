# Smoke Run Protocol v1.1 (Rerun)

**目的**: 驗證 receipt v1 schema + env taxonomy + repro pre-flight 在真實執行上的可用性
**任務數**: 5 題（同 P0-alpha）
**狀態**: 待執行

---

## 新增驗證項

除原有的 receipt schema 驗證外，本次 rerun 驗證：

1. **Env taxonomy 分類**：每筆 env failure 都有精確 taxonomy 值（`DEPENDENCY_MISMATCH` / `TOOLCHAIN_MISSING` / 等），不再是單桶 `REPRO_ENVIRONMENT_FAILURE`
2. **Repro pre-flight gate**：`ReproPreflightDiagnosis.diagnose()` 正確判定 `can_enter_patch_lane`
3. **Recipe registry**：已知 env failure 可被 recipe match

## Smoke Run 清單（同 P0-alpha）

| # | Instance ID | Project | Expected |
|---|------------|---------|----------|
| 1 | sympy__sympy-12489 | sympy | REPRO_ENVIRONMENT_FAILURE → taxonomy 分類 |
| 2 | psf__requests-2317 | psf | REPRO_ENVIRONMENT_FAILURE → taxonomy 分類 |
| 3 | astropy__astropy-14365 | astropy | SEARCH_HAS_PLACEHOLDER → patch_mismatch |
| 4 | django__django-11099 | django | ✅ solve（驗證 receipt v1 完整性） |
| 5 | matplotlib__matplotlib-23299 | matplotlib | REPRO_NOT_REPRODUCED → taxonomy 分類 |

## 驗證標準

- [ ] 每筆 receipt 有 v1 required fields（task_id, simulated, claim_eligible, expected_stop_layer, observed_stop_layer, model_calls, wall_time_sec, timestamp）
- [ ] `simulated` 全部為 `false`
- [ ] `claim_eligible` 全部為 `true`
- [ ] Env failure 有 taxonomy 值（非舊版 `env_noise`）
- [ ] Repro pre-flight gate 正確判定 `can_enter_patch_lane`
- [ ] Aggregate rollup 能正確分桶 env vs patch failures
