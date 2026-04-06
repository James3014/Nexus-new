---
title: Ops - Wiki Link Integrity
type: ops
status: active
tags: [governance, sanity-check, links, orphans]
last_compiled: 2026-04-06
owner: agent
---

# Ops - Wiki Link Integrity

## One-sentence summary
本頁面描述 Nexus Wiki 內部的鏈接完整性稽核標準，包括孤立頁面與損壞的 Wiki 鏈接監控。 [Source: scripts/ops/wiki_link_audit.py]

## Role / responsibility
- **連結導航驗證**: 確保 Wiki 內部所有導航路徑均可正確跳轉。
- **遺落頁面檢核**: 識別無任何入鏈 (Orphan) 的條目以防知識碎片化。
- **一致性監核**: 當檔案系統變動時，及時同步 Wiki 的引用真值。

## Integrity Matrix (連結完整性矩陣)
| Category | Metric | Warning Threshold | Audit Script |
|---|---|---|---|
| **Orphan Pages** | 0 inbound links | > 5 | `wiki_link_audit.py` |
| **Broken WikiLinks**| Target missing | > 0 | `wiki_link_audit.py` |

## Upstream
- **[[System Overview]]**: 總覽。
- **[[Ops - Wiki Drift Audit]]**: 物理路徑稽核。

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 作為發版前的「鏈接健康」警告。

## Related modules / files
- `/Users/jameschen/Workspace/nexus/scripts/ops/wiki_link_audit.py`: 主稽核腳本。

## Source notes
- v22 Engine Spec Part 7: 規定所有治理文檔必備全局入鏈。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **False Positives**: 暫時手動排除 `99_Schema` 與部分臨時 Changelog 頁面的孤立警報。
