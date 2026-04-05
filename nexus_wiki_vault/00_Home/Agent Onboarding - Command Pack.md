---
title: Agent Onboarding - Command Pack
aliases: [Command Runbook, Essential Commands, Command Pack]
type: home
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: scripts/engine/nexus_cli.py
related_pages:
  - "[[System Overview]]"
  - "[[Agent Onboarding - Implementation Map]]"
  - "[[Ops - CI Failure Playbook]]"
tags: [home, onboarding, commands, runbook]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Agent Onboarding - Command Pack

## One-sentence summary
本頁提供 Nexus Agent 新手進場的核心指令包，涵蓋環境檢查、Wiki 治理與發版校驗。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **標準執行流**: 確保新 Agent 能以一致的命令路徑完成系統初始化與修改驗證。 [Source: scripts/engine/nexus_cli.py]
- **防錯引導**: 提供 `dry-run` 優先的執行習慣。

## 🛡️ Phase 1: 環境與健康檢查 (Health Check)
```bash
uv run scripts/ops/ci_gate.py --dry-run [Source: scripts/ops/ci_gate.py]
```

## Upstream
- **Nexus CLI**: `scripts/engine/nexus_cli.py` 定義核心入口。 [Source: scripts/engine/nexus_cli.py]

## Downstream
- **[[Ops - CI Failure Playbook]]**: 若命令失敗，請前往此頁搜尋修復。

## Related modules / files
- `scripts/ops/wiki_linter.py`: 治理檢查。 [Source: scripts/ops/wiki_linter.py]

## Source notes
- v22 Engine Spec: 要求所有指令必須具備物理來源。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Interactive**: 是否提供互動式選單。
