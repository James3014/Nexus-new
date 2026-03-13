# Muse-Nexus Migration Safety Validator Plan

## Purpose

這份文件定義一個獨立驗證腳本的規劃，用來保護「系統自我升級」過程。

建議腳本名稱：

- `scripts/core/migration_safety_validator.py`

## Why It Exists

單靠人工 review 很難穩定發現：

- 半升級狀態
- 缺 default 欄位
- legacy task 缺欄位 crash
- external path 沒關乾淨
- 自修改超出允許範圍

因此需要一個專門的 migration safety check。

## First-Cut Responsibilities

### 1. Baseline freeze check

確認每個 implementation slice 開始前有記錄：

- baseline commit SHA
- baseline smoke command
- baseline `.muse_state` sample

### 2. Contract default check

驗證：

- 新增欄位是否有 default
- 缺欄位讀取是否安全

### 3. Half-upgraded state simulation

Scenario A:

- state 有新欄位，但 phase 還未使用

Scenario B:

- Context Hub 期待新欄位，但輸入是 legacy task

Expected result:

- no crash
- best-effort fallback

### 4. External-off safety check

驗證：

- external path 未啟用時，internal-only 模式仍能跑
- `external_needed == true` 但沒有 provider 時，不應直接爆炸

### 5. Scope guard

檢查第一波 implementation 是否超出允許檔案範圍。

First-cut allowlist:

- `scripts/core/state_contracts.py`
- `scripts/core/state_io.py`
- `scripts/core/context_hub.py`
- `scripts/core/reflection_store.py`
- `scripts/core/skills_router.py`
- `scripts/codex_loop_brain.py`
- `scripts/drclaw_diagnosis.py`

## Suggested CLI

```text
python3 scripts/core/migration_safety_validator.py --mode first-cut
```

Optional modes:

- `--mode first-cut`
- `--mode legacy-compat`
- `--mode half-upgrade`

## Suggested Output

```json
{
  "status": "failed",
  "checks": [
    {
      "name": "contract_default_check",
      "status": "passed"
    },
    {
      "name": "half_upgrade_simulation",
      "status": "failed",
      "reason": "legacy task missing steps_history caused KeyError"
    }
  ]
}
```

## When To Run

- 在每個 first-cut implementation slice 之後
- 在 merge 前
- 在修改 repair core loop 後必跑

## Practical Conclusion

Migration Safety Validator 的角色不是取代測試，而是：

> 專門保護「系統改自己」時最容易踩爆的相容性與半升級風險。
