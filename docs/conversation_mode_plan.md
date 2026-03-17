# Conversation Mode Plan

**Status: Implemented (v1.6 MVP — Verified)**
**Last Updated: 2026-03-17**

---

## Overview

Conversation Governance 作為 P-D-X-R-A-C lifecycle 的 task specialization，
不建立平行 chat subsystem，而是沿用現有 State Contract、ContextHub、Reviewer、Engine。

---

## Implemented Components (v1.6 MVP)

| 組件 | 狀態 | 關鍵方法 |
|---|---|---|
| `NexusState` helpers | ✅ Implemented | `init_conversation()`, `get_conversation_metadata()`, `update_conversation_metadata()` |
| `ContextHub` conversation pack | ✅ Implemented | `assemble_conversation_pack(audit_mode=False/True)` |
| `ContextHub` pre-routing | ✅ Implemented | `make_pre_routing_decision()` → `audit_level: skip/light/full` |
| `CodexLoopV2` conversation bypass | ✅ Implemented | `mode="conversation"` → 跳過 git/linter，走獨立 audit prompt |
| `NexusEngine` dynamic routing | ✅ Implemented | REJECTED + `return_target_phase` → D / X / R |
| Persistence | ✅ Implemented | `StateIO.save_global_state()` 在每個 metadata 更新後觸發 |

---

## Design Decisions

1. **Task Specialization, not Parallel System**: conversation 是 task type，不是獨立 subsystem。
2. **Risk-Based Audit**: `skip` → `light` → `full` 三層，根據 conversation 狀態動態決定。
3. **Minimal Schema Invasion**: `metadata["conversation"]` 是唯一新增容器，不修改頂層 Pydantic schema。
4. **Validator Compatibility**: `steps_history` 在 `current_phase` 更新後同步，避免 forbidden transition。

---

## Next Phase (v2.0 — Optional)

- 獨立治理層 (conversation governance layer) 以降低 Engine 責任
- Multi-turn memory compression 策略
- Conversation crystal 自動分類
