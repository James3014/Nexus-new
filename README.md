# Muse-Nexus

Muse-Nexus 目前是一套以本機腳本為核心的 coding operations system，重點能力集中在：

- worktree / git 隔離
- diagnosis / repair / audit loop
- Obsidian + LanceDB 記憶檢索
- 本機 dashboard / war room 類觀測介面

目前 repo 已具備多個核心能力，但尚未完全收斂成目標中的 `Commander + Context Hub + P-D-X-R-A-C + .muse_state` 架構。

## Repo Structure

```text
Muse-Nexus/
├── README.md
├── .gitignore
├── docs/
│   ├── 00_PROJECT_INDEX.md
│   ├── 01_CURRENT_STATE.md
│   ├── 02_TARGET_ARCHITECTURE.md
│   ├── 03_GAP_ANALYSIS.md
│   ├── 04_REFACTOR_ROADMAP.md
│   ├── 05_BACKLOG.md
│   ├── 06_REPO_CLEANUP_PLAN.md
│   ├── 07_SCRIPT_OWNERSHIP_MAP.md
│   └── 08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md
└── scripts/
```

## Docs

- [Project Index](./docs/00_PROJECT_INDEX.md)
- [Current State](./docs/01_CURRENT_STATE.md)
- [Target Architecture](./docs/02_TARGET_ARCHITECTURE.md)
- [Gap Analysis](./docs/03_GAP_ANALYSIS.md)
- [Refactor Roadmap](./docs/04_REFACTOR_ROADMAP.md)
- [Backlog](./docs/05_BACKLOG.md)
- [Repo Cleanup Plan](./docs/06_REPO_CLEANUP_PLAN.md)
- [Script Ownership Map](./docs/07_SCRIPT_OWNERSHIP_MAP.md)
- [Migration Runbook v1.5.2+](./docs/08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md)
- [State Contract Draft](./docs/09_STATE_CONTRACT_DRAFT.md)

## Current Position

這個 repo 現在比較接近：

```text
Intent
  -> codex loop / worktree manager
  -> diagnosis / repair / audit scripts
  -> memory recall
  -> dashboard / event summary
```

而不是：

```text
Intent
  -> Commander
  -> Context Hub
  -> phase state machine
  -> .muse_state contracts
  -> skills router
```

這份文件集的目的，是先把現況、缺口、演進順序寫清楚，讓後續不論由誰實作，都能在同一個專案目錄下接手。
