---
id: 02_target_architecture
type: doc
status: active
created: 2026-04-07T07:29:31Z
updated: 2026-04-07T07:29:31Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/02_TARGET_ARCHITECTURE.md
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
# Nexus v9 Target Architecture: Autonomic Evolution

## Target Definition

目標中的 Nexus v9 是一個具備「自我演進」能力的 coding workflow 系統，其核心支柱為：

- **Autonomic Commander**: 具備自愈能力的任務調度者。
- **[[Module - Intelligence and Context Core|Context Hub]]**: 聚合環境資訊的上下文中心。
- **P-D-R-A-C Workflow**: 正式化的自主演進流程。
- **Crystal Analyzer**: 將 tracelog 轉化為職能權重的學習引擎。
- **Fallback Resilience Chain**: 高可用的 Top-K 備援執行鏈。

## High-Level Shape (v9)

```text
Intent
  -> Commander (Autonomic)
  -> Plan
  -> Diag
  -> External Research (optional)
  -> Repair (with Fallback Chain)
  -> Audit
  -> Crystal (Active Learning Cycle)
  -> Experience crystallization / autonomic_weights.json
```

## Core Components (v9)

### Autonomic Commander

Role:
- 任務入口與 P-D-R-A-C 循環管理者。
- 具備 **Fallback 策略能力**：當 Top-1 職能失效時，自動切換至備援。
- 維護 `.muse_state` 與 `autonomic_weights.json`。

### [[Module - Intelligence and Context Core|Context Hub]]

Role:
- 依 phase 組裝 context pack。
- 整合 `task_id`、`files` 等即時訊號提供給 `SkillsRouter` 進行 Bonus 計分。

### Crystal Analyzer (v9 Learning Core)

Role:
- **經驗結晶化**：分析 `tracelog.jsonl` 與 `reflection.jsonl` 的執行結果。
- **動態調權**：根據成功/失敗訊號，自動修正 `SkillsRouter` 的決策權重。
- 透過 `nexus:crystal` 指令觸發。

### Skills Router (v9 Top-K)

Role:
- **Top-K Routing**：回傳前 K 個候選職能而非單一解。
- **環境感知計分**：由 `autonomic_weights.json` 提供基礎分，環境訊號提供獎勵分。

## 🏗️ v9 State Layout

```text
.muse_state/
├── plan.json
├── diagnosis.json
├── autonomic_weights.json  <-- [v9 Core]
├── tracelog.jsonl         <-- [v9 Learning Input]
├── reflection.jsonl
├── repair_final.json
└── skills_used.json
```

## 🏗️ Factory Scaling (Night Shift Mode)

為了支援工業級規規模化，架構整合了以下組件：

### Factory Router
- **智慧調度**: 優先處理 Hotfix (Priority 0)，並根據模型 Quota 進行併發管理。
- **SQLite Queue Manager**: 確保任務狀態原子化。

### Batch Guard & Monitor
- **Tmux Isolation**: 實現物理級別的預算與環境隔離。
- **WarRoom Monitoring**: 實時監控 Token 消耗、Strike 次數與職能命中率。

## Architectural Principle (v9)

> **自主演進、備援韌性、經驗結晶。**

Nexus v9 不再僅是工具的堆疊，而是一個能與項目共同成長、在錯誤中自我修復的自適應生命體。


---
[[System Overview]]