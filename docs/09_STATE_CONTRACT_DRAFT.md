# Muse-Nexus State Contract Draft

## Purpose

這份文件定義 Muse-Nexus v1.5.2+ 遷移期間建議新增的 state contract 草案。

目標不是一次做成嚴格 validator，而是先把：

- 欄位名稱
- 結構形狀
- 預設值策略
- 向後相容原則

寫清楚，讓不同 phase、Commander、Context Hub、War Room、skills router 對同一份 state 有共同理解。

## Core Rules

### 1. JSON is the only authority format

以下檔案一律使用 JSON 或 JSONL：

- `plan.json`
- `diag_context_pack.json`
- `diagnosis.json`
- `research_pack.json`
- `repair_context_pack.json`
- `repair_final.json`
- `audit_context_pack.json`
- `audit_result.json`
- `skills_used.json`
- `trace_log.jsonl`
- `reflection.jsonl`

### 2. Append-first evolution

新增 schema 時遵循：

- 先加欄位，不改既有 key 語義
- 舊欄位保留，必要時用 optional 讀取
- 新欄位應有合理 default

### 3. Legacy task compatibility

舊任務可能沒有：

- `skills_used`
- `external_used`
- `reflection`
- `steps_history`
- `research_pack`

讀取端必須支援：

- `.get("field", default)`
- 缺欄位時採 best-effort 行為

## Recommended Top-Level State Shape

```json
{
  "schema_version": "1.5.2-rc",
  "task_id": "muse_upgrade_v1_5_2_plus",
  "current_phase": "R",
  "current_step_id": "repair.round.3",
  "steps_history": [],
  "external_needed": false,
  "external_used": [],
  "skills_used": [],
  "research_pack_ref": ".muse_state/research_pack.json",
  "reflection_ref": ".muse_state/reflection.jsonl"
}
```

這裡的 top-level state 可由 Commander 維護，作為 phase navigation 與 War Room 摘要的最小索引。

## Field Drafts

### `schema_version`

Type:

- `string`

Examples:

- `"1.5.1"`
- `"1.5.2-rc"`
- `"1.5.2"`

Rule:

- 在未完全打通所有 phase 前，可先用 rc 標記
- 不要求所有 legacy tasks retroactively 升版

### `current_phase`

Type:

- `string`

Allowed values:

- `"P"`
- `"D"`
- `"X"`
- `"R"`
- `"A"`
- `"C"`

Default:

- `"P"` for new task

### `current_step_id`

Type:

- `string | null`

Examples:

- `"plan.bootstrap"`
- `"diag.run_smoke"`
- `"repair.round.2"`
- `"audit.guard_pass"`

Purpose:

- 給 Commander / War Room 顯示更細粒度進度

### `steps_history`

Type:

- `array<object>`

Suggested shape:

```json
[
  {
    "phase": "D",
    "step_id": "diag.run_smoke",
    "status": "completed",
    "started_at": "2026-03-13T14:21:00Z",
    "ended_at": "2026-03-13T14:21:08Z",
    "summary": "Smoke command failed with FastAPI dependency mismatch."
  }
]
```

Suggested keys:

- `phase`
- `step_id`
- `status`
- `started_at`
- `ended_at`
- `summary`
- `error`

Allowed `status` values:

- `pending`
- `in_progress`
- `completed`
- `failed`
- `skipped`
- `compensated`

### `external_needed`

Type:

- `boolean`

Meaning:

- 當前 phase 或 diagnosis 判斷需要外部世界知識，但未必已經真的調用外部工具

Default:

- `false`

### `external_used`

Type:

- `array<object>`

Suggested shape:

```json
[
  {
    "phase": "D",
    "provider": "felo",
    "mode": "search",
    "query": "fastapi dependency override test client error",
    "status": "success",
    "research_pack_id": "rp_20260313_001",
    "timestamp": "2026-03-13T14:25:13Z"
  }
]
```

Suggested keys:

- `phase`
- `provider`
- `mode`
- `query`
- `status`
- `research_pack_id`
- `timestamp`
- `latency_ms`
- `error`

TOON-friendly:

- yes

Reason:

- 屬於平坦 records，適合 Context Hub 在 prompt 中壓縮成表格視圖

### `skills_used`

Type:

- `array<object>`

Suggested shape:

```json
[
  {
    "phase": "P",
    "skill": "aibdd.spec.user-story.gen",
    "reason": "input_is_fuzzy",
    "input_ref": "task_metadata",
    "output_ref": ".muse_state/plan.json#spec_context.user_story_path",
    "status": "success",
    "timestamp": "2026-03-13T14:10:05Z"
  }
]
```

Suggested keys:

- `phase`
- `skill`
- `reason`
- `input_ref`
- `output_ref`
- `status`
- `timestamp`
- `summary`
- `error`

TOON-friendly:

- yes

### `research_pack.json`

Type:

- `object`

Suggested shape:

```json
{
  "research_pack_id": "rp_20260313_001",
  "type": "for_diag",
  "query_context": "FastAPI dependency override regression",
  "api_facts": [
    "Dependency override must be applied before client creation."
  ],
  "spec_clarifications": [
    "Issue is framework behavior, not local business logic."
  ],
  "sources": [
    {
      "title": "FastAPI Testing Dependencies",
      "url": "https://example.com",
      "snippet": "Use app.dependency_overrides before TestClient init.",
      "relevance": 0.93
    }
  ],
  "generated_at": "2026-03-13T14:26:00Z",
  "provider": "felo"
}
```

Suggested top-level keys:

- `research_pack_id`
- `type`
- `query_context`
- `api_facts`
- `spec_clarifications`
- `sources`
- `generated_at`
- `provider`

Allowed `type` values:

- `"for_diag"`
- `"for_repair"`
- `"for_audit"`
- `"general"`

TOON-friendly:

- partially

Guidance:

- `sources` array 適合在 prompt 中轉 TOON
- 整個 pack 本身仍維持 JSON

### `reflection.jsonl`

Type:

- `jsonl`

One-line record shape:

```json
{
  "round_id": 3,
  "phase": "R",
  "summary": "Tried timeout tuning; still failing with 500.",
  "negative_constraints": [
    "Do not keep increasing timeout blindly"
  ],
  "used_research_ids": [
    "rp_20260313_001"
  ],
  "files_touched": [
    "app/api/test_client.py"
  ],
  "test_result": "failed",
  "timestamp": "2026-03-13T14:31:00Z"
}
```

Suggested keys:

- `round_id`
- `phase`
- `summary`
- `negative_constraints`
- `used_research_ids`
- `skills_used`
- `files_touched`
- `test_result`
- `timestamp`

TOON-friendly:

- yes

Guidance:

- JSONL 作為權威記錄
- Context Hub 可只取最近 N 條摘要後轉成 TOON prompt view

### `diag_context_pack.json`

Suggested keys:

- `task_goal`
- `failure_signature`
- `hotspots`
- `pseudo_flows`
- `needs_research`
- `skills_used`
- `lessons`

### `repair_context_pack.json`

Suggested keys:

- `task_goal`
- `root_cause`
- `repair_strategy`
- `state_diff`
- `recent_reflections`
- `research_summary`
- `code_quality_report`
- `negative_constraints`
- `skills_used`

### `audit_context_pack.json`

Suggested keys:

- `repair_status`
- `target_tests_status`
- `smoke_status`
- `research_summary`
- `code_quality`
- `prior_audit_failures`
- `skills_used`

## Suggested Python-Level Modeling

如果未來要在 `state_contracts.py` 中落地，建議先從寬鬆 TypedDict 或 dataclass 開始，而不是一開始就上嚴格 validator。

Suggested order:

1. `TaskState`
2. `StepRecord`
3. `SkillUsageRecord`
4. `ExternalUsageRecord`
5. `ResearchPack`
6. `ReflectionRound`

## Prompt Compression Guidance

可以在 Context Hub 中選擇性將以下欄位轉成 TOON 視圖：

- `reflection.jsonl` 最近 N 條
- `research_pack.sources`
- `skills_used`
- `external_used`

不得轉換的層：

- `.muse_state` 寫入格式
- `state_contracts.py` 權威 schema
- phase 之間的檔案交換格式

## Open Decisions

- [ ] top-level task state 是否獨立成 `task_state.json`
- [ ] `skills_used` 是否獨立檔案，或嵌入各 phase context pack
- [ ] `reflection` 最終保留 JSONL 還是再加摘要 JSON
- [ ] `research_pack` 是否一任務一份，或每 phase 一份
- [ ] `steps_history` 是否寫在 top-level state，還是由 `trace_log.jsonl` 派生

## Practical Conclusion

這份 contract draft 的目的不是一次把 schema 鎖死，而是先建立：

> phase 能共享、Commander 能導航、Context Hub 能組裝、War Room 能顯示、skills router 能回寫

的共同最小語言。
