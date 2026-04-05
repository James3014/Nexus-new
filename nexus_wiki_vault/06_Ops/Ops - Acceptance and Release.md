---
title: Ops - Acceptance and Release
aliases: [Release Gate, Acceptance Policy]
type: ops
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: scripts/ops/nexus_release_gate.sh
related_pages:
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[Protocol - Evidence Map]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [ops, release, acceptance, gate]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Ops - Acceptance and Release

## One-sentence summary
本頁定義 Nexus 軟體正式封版與發布的流程，對齊測試、審計、Manifest 與環境清理的硬性要求。 [Source: Spec v22 Part 8]

## Role / responsibility
- **發布阻斷**: 在未滿足 `Promotion Gate` 指標前禁止執行 `git tag`。 [Source: `nexus_release_gate.sh`]
- **環境清場**: 要求發布前工作區 (Worktree) 必須 100% 乾淨且通過 `git audit`。 [Source: Release Discipline]
- **同步確認**: 確保 Wiki 與 Repo 之內的 README 與 Spec 已同步更新。 [Source: Documentation Governance]

## Upstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供晉升核准。
- **Build Server**: 完成底層封裝。

## Downstream
- **Production Environment**: 正式部署。
- **Release Registry**: 更新全域版本號。 [Source: `Source Index`]

## Related modules / files
- `scripts/ops/nexus_release_gate.sh`: 正式發布腳本。 [Code: `nexus_release_gate.sh`]
- `scripts/ops/nexus_completion_gate.py`: 任務完成檢核器。 [Code: `nexus_completion_gate.py`]

## Source notes
- Hardened v17.1 Spec: 定義 acceptance reports 的結構要求。
- v22 Engine Spec: 確立「無證據不發布」的核心紀律。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Hotfix Policy**: 針對緊急修復是否允許 Bypass 部分門禁指標。
- [ ] **Staging Layer**: 是否需要在 Production 前新增一個 Staging 相位。
