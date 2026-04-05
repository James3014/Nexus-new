---
title: Module - Implementation Responsibility Matrix
aliases: [Implementation Matrix, File-to-Responsibility Map]
type: module
status: active
version_scope: [v22, v23]
source_of_truth: scripts/engine/nexus_cli.py
related_pages:
  - "[[System Overview]]"
  - "[[Agent Onboarding - Implementation Map]]"
  - "[[Module - Core Orchestrator Deep Dive]]"
  - "[[Module - Guard and Gate Control]]"
  - "[[Module - Memory Pipeline Deep Dive]]"
  - "[[Module - Policy and Learning Governance]]"
  - "[[Module - State Contracts]]"
  - "[[Ops - CI/CD Promotion Gate]]"
tags: [module, implementation, matrix, ownership]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - Implementation Responsibility Matrix

## One-sentence summary
本頁用「檔案 -> 職責 -> 產物 -> 驗證」矩陣，讓新 Agent 直接定位 Nexus 實作邏輯與治理連結。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- 將抽象架構分解成可讀、可驗證的責任邊界。 [Source: nexus/core/orchestrator.py]
- 降低新 Agent 在 `nexus/core/` 大量模組中的搜尋成本。 [Source: nexus/core/state_repository.py]
- 提供每個責任區對應的最小驗證命令。 [Source: scripts/ops/ci_gate.py]

## Upstream
- 架構層定義來自 `[[System Overview]]`。 [Source: nexus_wiki_vault/00_Home/System Overview.md]
- 流程層定義來自 `[[Flow - PXDRAC Runtime]]`。 [Source: nexus_wiki_vault/03_Flows/Flow - PXDRAC Runtime.md]
- 治理約束來自 `[[Ops - CI/CD Promotion Gate]]`。 [Source: nexus_wiki_vault/06_Ops/Ops - CI/CD Promotion Gate.md]

## Downstream
- 新 Agent 可以先定責，再落到具體檔案閱讀與修改。 [Source: scripts/nexus_cli.py]
- 代碼變更可回連至對應工件與 CI gate 檢核。 [Source: scripts/ops/ci_gate.py]
- Wiki 可據此補齊 `[Source: path]`，避免描述漂移。 [Source: scripts/ops/wiki_linter.py]

## Related modules / files
- `scripts/nexus_cli.py`: 對外 CLI shim，轉接至 engine CLI。 [Source: scripts/nexus_cli.py]
- `scripts/engine/nexus_cli.py`: 主命令面與 protocol startup gate。 [Source: scripts/engine/nexus_cli.py]
- `nexus/core/orchestrator.py`: 審核主循環與模型回合控制。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_repository.py`: `NexusState` JSONL 持久化。 [Source: nexus/core/state_repository.py]
- `nexus/core/state_contracts.py`: state contract 型別基礎。 [Source: nexus/core/state_contracts.py]
- `nexus/core/policy_manager.py`: episode/policy 記錄與回注。 [Source: nexus/core/policy_manager.py]
- `nexus/core/memory/ingest.py`: 任務結果轉 episodic memory。 [Source: nexus/core/memory/ingest.py]
- `nexus/core/phase_health.py`: phase health 計算 facade。 [Source: nexus/core/phase_health.py]
- `.nexus/`、`manifest.json`: runtime 工件與最終封裝索引。 [Source: manifest.json]

## Source notes
- `scripts/engine/nexus_cli.py` 使用 Click 註冊 `nexus:*` 命令族，並在啟動時執行 protocol gate。 [Source: scripts/engine/nexus_cli.py]
- `nexus/core/orchestrator.py` 中 `_do_loop` 管理 strike/retry 與 token 計量彙整。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_repository.py` 的 `load()` 以最後一行作為最新狀態。 [Source: nexus/core/state_repository.py]
- `nexus/core/policy_manager.py` 會在 `record_episode` 階段更新 learning metadata。 [Source: nexus/core/policy_manager.py]
- `scripts/ops/ci_gate.py` 將 wiki audit、tests、benchmark、evidence integrity 串成單一路徑。 [Source: scripts/ops/ci_gate.py]

## LanceDB implementation boundary (as-is vs proposal)
- **已落地（repo 可驗證）**: `.nexus/memory/memory_index.lancedb`、`nexus/services/memory_indexer.py`、`nexus_swarm/wisdom/lancedb_store.py`。 [Source: nexus/services/memory_indexer.py]
- **已落地（Desk 表徵）**: `nexus-desk/src-tauri/src/main.rs` 目前有 `phase_health_source` 欄位與 Desk view model。 [Source: nexus-desk/src-tauri/src/main.rs]
- **未落地（提案/外部文件）**: `scripts/embed_run.py`、`war_armor` table、`ArmorComparison.tsx` 目前不在本 repo。 [Source: nexus_wiki_vault/90_Sources/Source - Nexus Anti Registry.md]
- **治理規則**: 未落地提案僅可放在來源登記或 roadmap，不可寫成核心真值。 [Source: scripts/ops/wiki_linter.py]

## Open questions / conflicts
- [x] **子域 Ownership Map**: 已建立 `orchestrator`, `guard`, `memory`, `policy` 四大深描頁。
- [ ] `manifest.json` 與 `.nexus/release_manifest.json` 的角色邊界是否要在本頁明文化。
- [ ] v23 智慧層相關模組是否應獨立一張 matrix（避免與穩定層混雜）。
- [ ] 是否將 LanceDB multi-armor proposal 轉成實作 RFC，再決定是否進入 production contract。

## Responsibility Matrix
| Layer | Primary file | Responsibility | Main artifact | Verify |
|---|---|---|---|---|
| CLI Entry | `scripts/nexus_cli.py` | 舊介面相容與入口轉接 | CLI process | `uv run scripts/nexus_cli.py nexus:status` |
| Command Surface | `scripts/engine/nexus_cli.py` | 命令群定義與 protocol gate | command result JSON/text | `uv run scripts/engine/nexus_cli.py nexus:probe` |
| Orchestration | `nexus/core/orchestrator.py` | review loop、strike、token 追蹤 | 參見 `[[Module - Core Orchestrator Deep Dive]]` | `uv run pytest tests/test_v9_regression_p1.py` |
| State Persistence | `nexus/core/state_repository.py` | `NexusState` 讀寫與回載 | state jsonl | `./nexus` state 檢核 |
| Policy & Governance | `nexus/core/policy_manager.py` | episode/policy 記錄與代謝 | 參見 `[[Module - Policy and Learning Governance]]` | `uv run scripts/ops/ci_gate.py --dry-run` |
| Memory Pipeline | `nexus/services/memory.py` | lancedb 語義檢索與 ingest | 參見 `[[Module - Memory Pipeline Deep Dive]]` | LanceDB FTS 測試 |
| Tool Governance | `nexus/core/capability_gate.py` | phase-based JIT 工具隔離 | 參見 `[[Module - Guard and Gate Control]]` | `python -c "from nexus.core.capability_gate..."` |
| Health Scoring | `nexus/core/phase_health.py` | PXDRAC phase health 更新 | phase metrics | benchmark health 欄位 |
| Governance Gate | `scripts/ops/ci_gate.py` | strict promotion chain | `ci_benchmark.csv` | `uv run scripts/ops/ci_gate.py --strict` |
