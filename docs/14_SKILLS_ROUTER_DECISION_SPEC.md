# Muse-Nexus Skills Router Decision Spec

## Purpose

這份文件把 `skills_router.py` 的決策規則先定成可驗證的 prototype，避免第一版 router 只是主觀 if/else。

目標不是一開始追求完美模型，而是：

- 先有一致規則
- 先能解釋為什麼某 skill 被選上
- 先能人工 review decision 是否合理

## Design Principle

第一版不做黑箱權重模型，先做：

- decision tree
- 簡單 scorecard
- 可輸出 decision reason

## Inputs

最低限度輸入：

- `phase`
- `language`
- `task_scale`
- `is_new_feature`
- `is_large_refactor`
- `stacktrace_pattern`
- `has_external_dependency_signal`
- `failure_signature`

Optional inputs:

- `has_user_story`
- `has_prd`
- `needs_sequence_reasoning`
- `existing_test_gap`
- `framework_name`

## First-Cut Decision Tree

### Phase P

If:

- input is fuzzy -> prefer:
  - `aibdd.spec.user-story.gen`
  - `aibdd.spec.prd.detail-req.gen`

If:

- cross-module interaction is high -> add:
  - `aibdd.spec.diagram.sequence-diagram.gen`

If:

- tech stack uncertainty is high -> add:
  - `aibdd.spec.tech-stack.gen`

### Phase D

If:

- stacktrace scope is large -> add:
  - `codebase_investigator`

If:

- hotspot logic is hard to read -> add:
  - `common.gen.pseudo-code`

### Phase R

If:

- language is python and task is new feature -> consider:
  - `aibdd.auto.python.e2e.red/green`
  - `aibdd.auto.python.unittest.pytest-bdd.feature`

If:

- task is large refactor -> consider:
  - `aibdd.auto.python.e2e.refactor`
  - `aibdd.auto.python.code-quality`

If:

- repeated quality issues after patch -> consider:
  - `aibdd.auto.python.code-quality`

### Phase A

If:

- language is python and static quality signal matters -> consider:
  - `aibdd.auto.python.code-quality`

## Scorecard Prototype

第一版可以給每個 skill 一個簡單分數：

```text
total_score =
  phase_weight
  + language_match
  + task_scale_weight
  + new_feature_weight
  + refactor_weight
  + stacktrace_match_weight
  + external_dependency_weight
```

Example scoring range:

- strong match: `+3`
- medium match: `+2`
- weak match: `+1`
- no match: `0`
- explicit mismatch: `-3`

Selection rule:

- `score >= threshold` 才入選
- 同時輸出 `reasons[]`

## Example Output Shape

```json
[
  {
    "skill": "codebase_investigator",
    "phase": "D",
    "score": 7,
    "threshold": 5,
    "reasons": [
      "stacktrace_scope_large",
      "hotspot_count_high"
    ],
    "output_target": ".muse_state/diag_context_pack.json#hotspots"
  }
]
```

## Review Rule

第一版 router 每次都應輸出：

- selected skills
- rejected candidates with key reason
- score breakdown

目的：

- 讓人工 reviewer 能快速看出 decision 是否合理

## First-Cut Constraints

- 第一版先只做 selection，不做 skill execution
- 不追求自動最佳化
- 不使用歷史學習自動調權重
- decision logic 需可手動閱讀與修改

## Validation Approach

應準備一組小型 case table，驗證 router decision：

- fuzzy feature request
- python large refactor
- large stacktrace diagnosis
- external API uncertainty
- simple internal bugfix

每個 case 都應有人類期望答案，與 router output 對照。

## Practical Conclusion

Skills Router 第一版的目標不是「聰明」，而是：

> 穩定、可解釋、可被人工校準。
