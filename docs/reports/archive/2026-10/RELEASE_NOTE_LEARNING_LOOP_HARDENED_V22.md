# Nexus Learning Loop Hardening v22.0

## 新增契約

- **`.nexus/knowledge/lesson_events.jsonl`**：Lesson machine-truth (SSoT)，Schema v1。
- **`.nexus/knowledge/.codex_lessons.md`**：Human-readable mirror，由 JSONL 自動同步。

## 注入座標

- **Phase C Crystallize**：`continuous_learning.py::persist_structured_lesson()`
- **Phase P Planner**：`planner.py::P10.5` lesson retrieval & context injection
- **Prompt Builder**：`build_task_prompt()` 自動解析 `retrieved_lessons.prompt_context`

## 治理保障

- **Idempotency**：SHA256 `lesson_id` 基於 `task_id + root_cause + corrective_action + patch_hash`
- **Token Safety**：Context 注入上限 800 tokens
- **Fallback**：無 lessons 時優雅降級，無影響既有流程

## 回退機制

1. `rm .nexus/knowledge/lesson_events.jsonl .nexus/knowledge/.codex_lessons.md`
2. 重啟任務，planner 自動 fallback 至無 lessons 模式

## 驗證基線

- Tests: 21/21 PASS (P1-A~P1-D regression green)
- Physical Simulation: confirmed `retrieved_lessons` injected into Planner Context during `auth timeout` task.
- Traceability: `lesson_id` and `task_id` are consistently mapped across the knowledge store and execution manifests.
