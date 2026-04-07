---
aliases:
- Artifact Chain
- SSoT Flow
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Evidence Map](Protocol - Evidence Map.md)|[[Protocol - [[Protocol - Evidence Map|Evidence
  Map]]|Protocol - [Evidence Map](Protocol - Evidence Map.md)]]]]'
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: MUSE-NEXUS-v22#DataFabric
status: active
tags:
- protocol
- evidence
- chain
- manifest
title: Protocol - Evidence Chain
type: protocol
version_scope:
- v17.1
- v22
- v23
---



# Protocol - Evidence Chain

## One-sentence summary
本頁定義 Nexus 證據鏈 (Evidence Chain) 的權威對索引順序、封印邏輯與 `manifest.json` 的穩定性規範。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **鏈式追蹤**: 確保 `manifest.json` 完整包含單次任務的所有子工件。 [Source: 00_Home/System Overview.md]
- **誠信校驗**: 透過 `write_proof.json` 驗證所有的文件寫入均為真實且已授權。 [Source: ci_gate.py]
- **歸檔準備**: 轉換為加密封印格式以供 Arweave 存儲。 [Source: 00_Home/System Overview.md]

## Upstream
- **[Protocol - Evidence Map](Protocol - Evidence Map.md)**: 提供依賴圖譜。
- **Phase Runners**: 提交通知至 Manifest Sealer。 [Code: nexus_cli.py]

## Downstream
- **Crystallizer (Phase C)**: 根據證據鏈萃取教訓。 [Code: nexus_crystal.py]
- **[[Ops - CI/CD Promotion Gate]]**: 作為晉升的實體依據。

## Related modules / files
- `nexus/core/manifest_factory.py`: 證據鏈封裝工廠。 [Code: manifest_factory.py]
- `scripts/ops/index_to_manifest.py`: 手動修復工具。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義原始「證據工件」清單。
- v22 Engine Spec: 確立 `SSoT` (Single Source of Truth) 必須表現為單一連通鏈。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Chain Fragmentation**: 當某一相位崩潰時，局部證據鏈的提取邏輯。
- [ ] **Encrypted Payload**: 是否應在 manifest 中包含工件的加密摘要而非純文字路徑。

---
[System Overview](../00_Home/System Overview.md)
