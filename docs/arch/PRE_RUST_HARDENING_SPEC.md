# 🛡️ Nexus Pre-Rust Hardening Specification (v1.0)
## From Governance Components to Autonomous Operating System

> **Status**: IN PROGRESS (Stage 3 Sealed)
> **Latest Commit SHA**: 88da83273
> **Nexus Identity**: 88da83273 + v3.2.3 RUNTIME-ALIGNED
> **Position**: This specification integrates engineering standards 9-15 to build a formalized "Front-end Operating System" before Rust migration.
> **Objective**: Implement programmable flow control, CRISPY documentation artifacts, and budget-aware autonomy.

---

## 1. 總體里程碑 (Program Milestones)

| 階段 | 名稱 | 核心目標 | 狀態 |
|---|---|---|---|
| **Stage 0** | Baseline Alignment | 對齊身份、版本與治理基線，消除文件分叉。 | **SEALED** |
| **Stage 1** | Intent & Flow Control | 實裝 `IntentIntakeClassifier` 與程式化狀態機。 | **SEALED** |
| **Stage 2** | CRISPY Documents | 實體化 `Questions`, `Research`, `Design`, `Outline`, `Plan` 產物。 | **SEALED** |
| **Stage 3** | Vertical Slice Planning| 強制垂直增量實作契約，禁止水平切分。 | **SEALED** |
| **Stage 4** | Instruction Budget | 實裝 `BudgetGovernor` 與自動 Compaction 記錄。 | **IN-PROGRESS** |
| **Stage 5** | Team Alignment Gate | 將人類對齊 (Human Review) 前移至設計與大綱階段。 | PLANNED |
| **Stage 6** | Rust Readiness | 產出 `RUST_MIGRATION_MAP_V1` 與模組分級。 | PLANNED |

---

## 2. 核心組件定義 (Core Components)

### C1. Intent Intake & Flow State Machine
- **Input**: User goal + route features.
- **Output**: `interaction_mode` (direct | clarify_first | outline_first).
- **Enforcement**: Orchestrator must block illegal state transitions (e.g., skip design).

### C2. CRISPY Artifact Chain
- **Questions.md**: Missing info/constraints only.
- **Research.md**: Facts-only analysis (zero design leakage).
- **Design.md**: Targets, trade-offs, and decisions (no implementation details).
- **StructureOutline.md**: Phases, order, and verification points (no per-line edits).
- **Plan.md**: Implementation details (must reference Design/Outline IDs).

### C3. Vertical Slice Contract
- Every slice must cross UI/API/Service/Data/Verify layers.
- Mandatory `verify_command` and `rollback_hint` per slice.
- `HORIZONTAL_SLICE_DETECTED` gate enforces incremental delivery.

---

## 3. 治理出口與 Blocker Codes
- `INDEX_MASTER_IDENTITY_MISMATCH`: Stage 0 身份分叉攔截。
- `CHECKPOINT_NOT_CONFIRMED`: 狀態機跳步攔截。
- `RESEARCH_CONTAINS_DESIGN`: 研究階段設計污染攔截。
- `HORIZONTAL_SLICE_DETECTED`: 水平切分大綱攔截。

---
**NEXUS IDENTITY: 88da83273 + v3.2.3 RUNTIME-ALIGNED**
