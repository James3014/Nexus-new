# 🗺️ Nexus Rust Migration Map (v1.0)

> **Status**: SEALED
> **Latest Commit SHA**: 58cc591b2
> **Nexus Identity**: 58cc591b2 + v3.2.6 RUNTIME-ALIGNED
> **Objective**: Categorize modules for systematic migration to the Rust Runtime while preserving fail-closed governance.

---

## 1. 模組遷移分級 (Migration Categories)

### 🚀 Category A: Move-Now (立即遷移)
*核心穩定、效能敏感、邏輯固定的基礎設施。*
- **AST Single-Pass Scanner**: 提升大文件掃描與符號提取速度。
- **Flow State Machine Shell**: 確保狀態轉移的原子性與不可繞過性。
- **Receipt/Evidence Verifier**: 提供物理級別的證據完整性校驗。
- **Socket/Process Monitoring**: 強化沙盒環境的硬即時監控。

### ⏳ Category B: Move-Later (後續遷移)
*結構已定、但仍需頻繁調校的編排與策略層。*
- **Baseline Replay Engine**: 待 Phase 7 基線完全凍結後遷入。
- **Vertical Slice Planner**: 待垂直切分契約成熟後遷入。
- **Contamination Guard**: 需要更強大的高效能正則/語義引擎。

### 🛑 Category C: Do-Not-Move-Yet (暫不遷移)
*高度變動、依賴大量外部 API 或具備高度策略靈活性的部分。*
- **Route Intelligence Policy**: 高頻調整的路由模型與權重。
- **Team Approval Workflows**: 涉及複雜人機互動介面的部分。
- **Budget Governor Policy**: 需根據 token 價格與 Provider 政策頻繁變動。

---

## 2. Readiness 準入檢查清單 (Readiness Checklist)
- [x] **Stage 0-5 Sealed**: 前置作業系統所有治理文件與收據機制已落地。
- [x] **Core Stability**: 核心掃描與狀態機模組在 100+ 任務中表現穩定。
- [x] **Boundary Clear**: Categories A 與 Categories C 之間的介面契約已定義。

---

## 3. Rust 遷移首批候選清單 (Primary Candidates)
| 模組名稱 | Python 原始位置 | Rust 目標組件 |
|---|---|---|
| `Matcher` | `nexus/services/local_heal/matcher.py` | `nexus-core-rs::matcher` |
| `FlowStateMachine` | `nexus/engine/flow_control.py` | `nexus-runtime-rs::flow` |
| `ReceiptVerifier` | `nexus/engine/capability_receipt_policy.py`| `nexus-audit-rs::verify` |

---
**NEXUS IDENTITY: 58cc591b2 + v3.2.6 RUNTIME-ALIGNED**
