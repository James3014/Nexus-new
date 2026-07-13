---
aliases: '[Onboarding, Command Runbook, Essential Commands, Command Pack]'
confidence: high
last_compiled: '2026-04-06'
lifecycle: superseded
owner: agent
related_pages: ''
source_of_truth: scripts/nexus_cli.py
status: active
superseded_by: 00_Home/AGENT_BOOTSTRAP.md
tags: '[home](System Overview.md), onboarding, commands, runbook]'
title: Agent Onboarding - Command Pack
type: '[home](System Overview.md)'
version_scope: '[v17.1, v22, v23]'
---

> **SUPERSEDED** — This page is replaced by [AGENT_BOOTSTRAP.md](AGENT_BOOTSTRAP.md) as the canonical Agent startup sequence. Preserved for historical reference. The startup sequence, task classes, and hard boundaries are defined in AGENT_BOOTSTRAP.



# Agent Onboarding - Command Pack

## One-sentence summary
本頁提供 Nexus Agent 新手進場的核心指令包，涵蓋環境檢查、Wiki 治理與發版校驗。 [Source: scripts/nexus_cli.py]

## Role / responsibility
- **標準執行流**: 確保新 Agent 能以一致的命令路徑完成系統初始化與修改驗證。 [Source: scripts/nexus_cli.py]
- **防錯引導**: 提供 `dry-run` 優先的執行習慣。

## 🧠 Phase 0: Context Injection (脈絡注入)
在執行任何指令前，Agent **必須**先建立系統心理模型。若無視背景脈絡直接執行指令，將被視為高風險行為。
- **架構掃描**: 閱讀 [System Overview](System Overview.md) 了解 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 治理邏輯。
- **地景確認**: 查閱 [Vault Topology](Vault Topology.md) 確認當前工作區在知識圖譜中的位置。
- **歷史溯源**: 若涉及核心協議修改，必須先查閱 [[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]] 確保不違反既有架構決策。

## 🛡️ Phase 1: 環境與健康檢查 (Health Check)
```bash
uv run scripts/ops/ci_gate.py --dry-run [Source: scripts/ops/ci_gate.py]
```

## Upstream
- **Nexus CLI**: `scripts/nexus_cli.py` 定義核心入口。 [Source: scripts/nexus_cli.py]

## Downstream
- **[Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)**: 若命令失敗，請前往此頁搜尋修復。

## Related modules / files
- `scripts/ops/wiki_linter.py`: 治理檢查。 [Source: scripts/ops/wiki_linter.py]

## Source notes
- v22 Engine Spec: 要求所有指令必須具備物理來源。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Interactive**: 是否提供互動式選單。

---
[System Overview](System Overview.md)

---
[[System Overview]]