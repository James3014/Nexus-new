---
title: Ops - Reference Boundary and Archive Policy
aliases: [Reference Boundary, Reference Archive Policy]
type: ops
status: active
version_scope: [v22, v23]
source_of_truth: repo-root
related_pages:
  - "[System Overview](../00_Home/System Overview.md)"
  - "[Source Index](../90_Sources/Source Index.md)"
  - "[Ops - Governance Changelog](Ops - Governance Changelog.md)"
tags: [ops, reference, archive, governance]
last_compiled: 2026-04-07
confidence: high
owner: agent
---
# Ops - Reference Boundary and Archive Policy

## One-sentence summary
定義 `Reference/` 的保留邊界與封存規則，避免非治理內容污染主線 Wiki。 [Source: Reference/README.md]

## Role / responsibility
- **邊界治理**: 僅允許治理核心參考文件留在 `nexus_wiki_vault/Reference/`。 [Source: scripts/ops/wiki_linter.py]
- **封存紀律**: 高噪音第三方資料移至 `/nexus_wiki_vault-quarantine_isolation/Reference_bulk_archive/`。 [Source: nexus_wiki_vault-quarantine_isolation/Reference_bulk_archive]

## Upstream
- **Wiki Merge/Sync 任務**: 批量同步容易導入 benchmark/worktree/vendor 文檔。 [Source: scripts/ops/ci_gate.py]
- **Reference 實際內容**: 以 `Reference/` 目錄為物理實體。 [Source: nexus_wiki_vault/Reference]

## Downstream
- **[Ops - Governance Changelog](Ops - Governance Changelog.md)**: 記錄每次 Reference 分層治理。 [Source: Reference/README.md]
- **[Source Index](../90_Sources/Source Index.md)**: 作為引用層級與來源治理說明入口。 [Source: nexus_wiki_vault/90_Sources/Source Index.md]

## Related modules / files
- `Reference/README.md`: Reference 入口。
- `nexus_wiki_vault/nexus_wiki_vault/Reference/docs/00_PROJECT_INDEX.md`: 最小 docs 索引。
- `/nexus_wiki_vault-quarantine_isolation/Reference_bulk_archive/`: 封存層。

## Source notes
- 主線治理門檻以 `wiki_linter --strict` 與 `ci_gate --dry-run` 為準。 [Source: scripts/ops/wiki_linter.py]
- Reference 保留核心頁：`README.md`, `QUICKSTART.md`, `program.md`, `task.md`, `walkthrough.md`, `.serena/memories/*`, `docs/00_PROJECT_INDEX.md`, `nexus_truth_dashboard.md`。 [Source: nexus_wiki_vault/Reference]

## Open questions / conflicts
- [ ] 是否需要將 `Reference` 進一步拆成 `Reference/Core` 與 `Reference/Imported`。
- [ ] 是否應增加自動封存腳本，避免下一次 merge 重複污染。


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]