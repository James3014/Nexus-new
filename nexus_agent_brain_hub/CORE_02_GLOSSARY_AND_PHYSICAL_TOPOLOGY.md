---
aliases:
- Terminology
- Nexus Terms
- Shared Vocabulary
confidence: high
last_compiled: 2026-04-07
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime|[[Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]
  Runtime|Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime]]]]'
- '[[Ops - Acceptance and Release|Ops - Acceptance and Release]]'
- '[[Ops - Truth Claims Register|Truth Claims]] Register|[[Ops - [[Ops - Truth Claims
  Register|Truth Claims]] Register|Ops - [[Ops - Truth Claims Register|Truth Claims]]
  Register]]]]'
source_of_truth: compiled
status: active
tags:
- system
- glossary
- terminology
title: Nexus Glossary
type: system
version_scope:
- v22
- v23
---



# Nexus Glossary

## One-sentence summary
本頁提供 Nexus 核心術語的單一語義定義，降低多代理協作中的用詞歧義與規約誤解。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **語義對齊**: 統一關鍵詞定義，避免不同 agent 產生衝突語意。
- **治理穩定**: 作為文件、CI 報告與任務回報的共用詞彙基準。

## Upstream
- `[[System Overview]]`: 全系統定位與版本邊界。
- `[[Flow - PXDRAC Runtime]]`: 執行相位定義。

## Downstream
- `[[Agent Boot Sequence]]`: 新 agent 啟動時快速對齊術語。
- `[[Ops - CI Failure Playbook]]`: 故障分類與修復語境一致化。

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`
- `.nexus/reports/acceptance_check.json`

## Source notes
- 建議固定詞義：
- `[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]`: Probe / eXplore / Diagnose / Repair / Audit / Crystallize 的任務生命週期。
- `P0 Drift`: 會阻斷發布的關鍵漂移問題。
- `Observe-only`: 樣本為 0 時不阻斷，但必須留下可追蹤證據（例如 `no_sample_observe_only=true`）。
- `Truth Claim`: 必須可由命令或實體路徑驗證的聲明。
- `[[task]] Contract`: 對任務交付範圍、命令、工件與變更路徑的約束。

## Open questions / conflicts
- [ ] 是否將 `PDRAC` (legacy) 與 `[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]` (current) 的差異固定為獨立術語頁。
- [ ] 是否建立術語版本化（v22/v23）避免未來升級時語義混淆。---
aliases:
- Deployment Architecture
- Physical Layout
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
- '[[Module - Core Orchestrator|Module - Core Orchestrator]]'
source_of_truth: ./
status: active
tags:
- system
- - - Vault Topology|topology
- physical
- layout
title: System - Physical [[Vault Topology|Topology]]
type: system
version_scope:
- v17.1
- v22
- v23
---



# System - Physical [[Vault Topology|Topology]]

## One-sentence summary
本頁描述 Nexus 系統在檔案系統、執行序與存儲節點上的實體佈局與核心目錄結構。 [Reference: compiled-[[Vault Topology|topology]]]

## Role / responsibility
- **路徑權威**: 定義 `./` 下的各目錄用途。 [Reference: [[System Overview]]]
- **執行隔離**: 描述 `.venv` 環境與 Core 邏輯的區隔。 [Source: scripts/engine/nexus_cli.py]
- **持久化映射**: 定義 `.nexus/` 目錄與 [[Module - Memory Repository|LanceDB]] 實體節點的關聯。 [Reference: [[Module - Memory Repository]]]

## Physical Directory Hierarchy

| Root Path | Category | Purpose | Source Provenance |
|---|---|---|---|
| `.nexus/` | **State** | 存儲所有運行時狀態、報告與證據。 | [Reference: Spec v22 Part 6] |
| `.nexus/knowledge/`| **SSoT** | 存放 `policymemory.jsonl` 等真值。 | [Reference: cleanup_policy_memory.py] |
| `.nexus/memory/` | **Vector** | [[Module - Memory Repository|LanceDB]] 向量資料庫節點。 | [Source: nexus/services/memory_indexer.py] |
| `nexus/` | **Logic** | 核心 Python 原始碼 (The Nerve)。 | [Source: 00_Home/System Overview.md] |
| `scripts/` | **Ops/Entry** | CLI 進入點與維運腳本。 | [Source: scripts/engine/nexus_cli.py] |
| `schemas/` | **Contract** | JSON Schema 權威定義中心。 | [Reference: [[State - Schemas]]] |

## Upstream
- **Deployment Spec**: 原始安裝與配置規範。
- **[[System Overview]]**: 提供宏觀佈局指引。

## Downstream
- **[[Module - Core Orchestrator]]**: 實體操作這些路徑。 [Code: 00_Home/System Overview.md]
- **[[System - Unknowns and Conflicts]]**: 登記路徑漂移或資源競爭問題。

## Related modules / files
- `./`: 系統根路徑。
- `nexus/core/errors.py`: 定義路徑缺失導致的 InfrastructureError。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義最初的 4 級目錄硬化結構。
- v22 Engine Spec: 引入 `.nexus/runs` 的階段化存儲路徑。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Permission Matrix**: 各目錄在不同用戶權限下的存取約束。
- [ ] **External Mount**: 部分龐大的向量資料庫是否應掛載於外部 Volume。