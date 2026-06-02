---
aliases:
- Gate Control
- Nexus Guard
- Security Gate
confidence: high
last_compiled: 2026-06-02
owner: agent
related_pages:
- '[Module - Security and Tool Guard Registry](Module - Security and Tool Guard Registry.md)'
- '[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)'
source_of_truth: src/governance/mod.rs
status: active
tags:
- core
- guard
- gate
- security
- access
- rust
title: Module - Guard and Gate Control
type: module
version_scope:
- v24.0
- v26
---

# Module - Guard and Gate Control (Hybrid v24.0)

## One-sentence summary
本頁解析 Nexus v24.0 的物理安全閘門實作，核心決策已全面下沉至 Rust Kernel，實現語義建議與物理裁決的絕對隔離。 [Source: src/governance/mod.rs]

## Role / responsibility
- **物理裁決 (Physical Enforcement)**: 透過 Rust `TransitionGuard` 強制執行合法狀態轉移，模型無權直接修改狀態。
- **語法隔離 (LangSec Guard)**: 透過 `IntentNormalizer` 驗證模型輸出是否符合 Formal Grammar，徹底阻斷自然語言幻覺。
- **Fail-Closed 預設**: 任何不合規、未知或低信心的語義標籤，一律強制引導至 `ESCALATE` 或 `STOP`。

## Governance Kernel Components (Rust 硬核組件)

| Logic Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **TransitionEngine** | 執行 P-X-D-R-A-C 狀態機計算，攔截非法跳步。 | [Source: src/governance/transition_engine.rs] |
| **BlockerEngine** | 判定政策性阻斷 (如 Horizontal Slice, design-in-research)。 | [Source: src/governance/blocker_engine.rs] |
| **ContractEngine** | 驗證各 Phase 輸出 Payload 的強型別完整性。 | [Source: src/governance/contract_engine.rs] |
| **IntentNormalizer** | **[LangSec]** 標籤識別與正規化，阻斷非正規文法。 | [Source: src/governance/normalizer.rs] |
| **SemanticAdapter** | 語義接口封裝，實施自動 Escalation 降級策略。 | [Source: nexus/engine/semantic_adapter.py] |

## Physical Enforcement Gate (物理強制執行 - Protocol v2.9)

依據 **🛡️ AGENT 強制執行規約 v2.9**，Nexus 採用「物理攔截」作為執行保障：
1. **標籤化通訊**: 模型僅輸出極簡標籤 (r:x, d:x, p:x)，不生成 JSON。
2. **三層測試網**: 每次提交必須通過 Rust Unit + Python Contract + E2E Regression。
3. **Escalation 逃生艙**: 任何異常（如超時、幻覺、對抗要求）自動觸發 `ESCALATE` 狀態。

## Source notes
- v24.0 Engine Spec: 要求治理裁決必須在 5ms 內由 Rust Kernel 完成，嚴禁在 Python 層進行二次邏輯修補。 [Source: docs/perplexity/RELEASE_NOTE_v2.3.md]

## Source notes
- v22 Engine Spec: 要求安全性檢查必須在工具真正執行前 10ms 內完成鎖定。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Bypass Scenarios**: 緊急維護模式下如何安全且可審計地繞過特定閘門。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]