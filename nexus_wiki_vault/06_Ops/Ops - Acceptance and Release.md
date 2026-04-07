---
aliases:
- Release Gate
- Acceptance Policy
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- Ops - CI/[Promotion Gate](Ops - CI/CD Promotion Gate.md)|[[CD [[CD Promotion Gate|Promotion
  Gate]]|CD [Promotion Gate](Ops - CI/CD Promotion Gate.md)]]]]
- '[Evidence Map](../05_Protocols/Protocol - Evidence Map.md)|[[Protocol - [[Protocol - Evidence Map|Evidence
  Map]]|Protocol - [Evidence Map](../05_Protocols/Protocol - Evidence Map.md)]]]]'
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: scripts/ops/nexus_release_gate.sh
status: active
tags:
- ops
- release
- acceptance
- gate
title: Ops - Acceptance and Release
type: ops
version_scope:
- v17.1
- v22
- v23
---



# Ops - Acceptance and Release

## One-sentence summary
本頁定義 Nexus 軟體正式封版與發布的流程，對齊測試、審計、Manifest 與環境清理的硬性要求。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **發布阻斷**: 在未滿足 `[Promotion Gate](Ops - CI/CD Promotion Gate.md)` 指標前禁止執行 `git tag`。 [Source: 00_Home/System Overview.md]
- **環境清場**: 要求發布前工作區 (Worktree) 必須 100% 乾淨且通過 `git audit`。 [Source: 00_Home/System Overview.md]
- **同步確認**: 確保 Wiki 與 Repo 之內的 [README](../../README.md) 與 Spec 已同步更新。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Upstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供晉升核准。
- **Build Server**: 完成底層封裝。

## Downstream
- **Production Environment**: 正式部署。
- **Release Registry**: 更新全域版本號。 [Source: nexus_wiki_vault/90_Sources/Source Index.md]]`]

## Related modules / files
- `scripts/ops/nexus_release_gate.sh`: 正式發布腳本。 [Code: 00_Home/System Overview.md]
- `scripts/ops/nexus_completion_gate.py`: 任務完成檢核器。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義 acceptance reports 的結構要求。
- v22 Engine Spec: 確立「無證據不發布」的核心紀律。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Hotfix Policy**: 針對緊急修復是否允許 Bypass 部分門禁指標。
- [ ] **Staging Layer**: 是否需要在 Production 前新增一個 Staging 相位。

---
[System Overview](../00_Home/System Overview.md)


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]