---
id: 15_migration_safety_validator_plan
type: doc
status: active
created: 2026-04-07T07:29:30Z
updated: 2026-04-07T07:29:30Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/15_MIGRATION_SAFETY_VALIDATOR_PLAN.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Muse-Nexus Migration Safety Validator Plan

## Purpose

這份文件定義一個獨立驗證腳本的規劃，用來保護「系統自我升級」過程。

建議腳本名稱：

- `scripts/core/migration_safety_validator.py`

## Priority

- 直接從 validator POC 起步
- 先有 CLI prototype，再擴充其他 phase integration

## [[why|Why]] It Exists

單靠人工 review 很難穩定發現：

- 半升級狀態
- 缺 default 欄位
- legacy [[task]] 缺欄位 crash
- external path 沒關乾淨
- 自修改超出允許範圍

因此需要一個專門的 migration safety check。

## First-Cut Responsibilities

### 0. Phase gatekeeper mode

Validator 應優先被定位成每個 phase 前的 gatekeeper，而不是事後補查工具。

Gate rule:

- P / D / R / A 每次進入前先跑 validator
- 若 state 不完整或相容性不成立，phase 不應繼續

Suggested invocation pattern:

```text
python3 scripts/core/migration_safety_validator.py --phase R --mode gatekeeper
```

Minimum gatekeeper checks:

- required state files present
- JSON shape readable
- legacy-safe defaults available
- current phase transition合法
- external-disabled fallback 可用
- touched files 未超出 first-cut allowlist

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

- [[Module - Intelligence and Context Core|Context Hub]] 期待新欄位，但輸入是 legacy [[task]]

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

Rule:

- gatekeeper mode 第一版只接受這 7 個核心檔案為允許修改範圍

## Suggested CLI

```text
python3 scripts/core/migration_safety_validator.py --mode first-cut
```

Optional modes:

- `--mode gatekeeper`
- `--mode first-cut`
- `--mode legacy-compat`
- `--mode half-upgrade`

Suggested flags:

- `--phase P|D|R|A|C`
- `--state-root .muse_state`
- `--baseline-file path`

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
      "reason": "legacy [[task]] missing steps_history caused KeyError"
    }
  ]
}
```

## When To Run

- 在每個 phase 開始前先跑 gatekeeper mode
- 在每個 first-cut implementation slice 之後
- 在 merge 前
- 在修改 repair core loop 後必跑

## Practical Conclusion

Migration Safety Validator 的角色不是取代測試，而是：

> 專門保護「系統改自己」時最容易踩爆的相容性與半升級風險。


---
[[System Overview]]