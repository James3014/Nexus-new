---
aliases:
- Retention Policy
- Artifact Provenance
- Data Lifecycle
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- nexus/learning/disk_policy.py
- nexus/learning/disk_janitor.py
- nexus/core/handoff_bundle.py
related_pages:
- Ops - CI/[[CD Promotion Gate|Promotion Gate]]|[[CD [[CD Promotion Gate|Promotion
  Gate]]|CD [[CD Promotion Gate|Promotion Gate]]]]]]
- '[[Protocol - Evidence Map|Evidence Map]]|[[Protocol - [[Protocol - Evidence Map|Evidence
  Map]]|Protocol - [[Protocol - Evidence Map|Evidence Map]]]]]]'
- '[[Module - Memory Repository|Module - Memory Repository]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: scripts/learning/cleanup_policy_memory.py
status: active
tags:
- ops
- retention
- provenance
- data-lifecycle
title: Ops - Artifact Retention and Provenance
type: ops
version_scope:
- v17.1
- v22
- v23
---



# Ops - Artifact Retention and Provenance

## One-sentence summary
本頁定義 Nexus 治理工件的物理生命週期、保留時限與權威溯源路徑，確保系統具備「可遺忘性」與「強可追蹤性」。

## Role / responsibility
- **容量治理**: 透過 TTL 機制防止 `.nexus/` 目錄與向量資料庫無限膨脹。
- **證據保鮮**: 確保 [[CD Promotion Gate|Promotion Gate]] 所需的核心證據在保留期內 100% 可用。
- **溯源校驗**: 定義工件回指原始規格或代碼的硬性連結規則。

## Artifact Conversion & Retention Matrix

| Artifact Category | Producer | Gate Criticality | Retention Path | Retention (TTL) | Source/Schema |
|---|---|---|---|---|---|
| **Policy Memory** | Crystallizer | MEDIUM | `.nexus/knowledge/policymemory.jsonl` | 90 Days | `cleanup_policy_memory.py` |
| **Run Manifests** | Sealer | **CRITICAL** | `.nexus/runs/*/manifest.json` | 90 Days | `manifest_schema.json` |
| **Handoff Bundles**| Orchestrator| **CRITICAL** | `.nexus/state/handoff_*.json` | 30 Days | `handoff_bundle.py` |
| **[[SKILL]] Outcomes** | Monitor | MEDIUM | `.nexus/metrics/skill_outcome_*.jsonl` | 90 Days | `disk_policy.py` |
| **Archived Skills**| Janitor | LOW | `skills/archived/*.md` | 90 Days | `disk_janitor.py` |

## Retention Mechanisms
- **DiskJanitor Service**: 每 24 小時執行一次，掃描 `retention_days` (Default 90) 之前的過期文件。 [Source: disk_janitor.py]
- **Atomic Cleanup**: `cleanup_policy_memory.py` 採用原子替換方式清理 JSONL，確保數據一致性。 [Source: 00_Home/System Overview.md]

## Upstream
- **Disk Policy Configuration**: 定義全域 `NEXUS_DISK_RETENTION_DAYS`。
- **System Time**: 依賴 UTC 時間戳進行 Cutoff 計算。

## Downstream
- **[[Module - Memory Repository]]**: 同步執行 90 天窗口的向量索引清理。
- **[[Ops - CI/CD Promotion Gate]]**: 依賴 Retention Path 內的證據進行晉升審計。

## Related modules / files
- `nexus/learning/disk_janitor.py`: 實體清理執行者。
- `scripts/learning/cleanup_policy_memory.py`: 策略記憶專屬清理。

## Source notes
- disk_policy.py: 定義默認 `retention_days = 90`。
- handoff_bundle.py: 規定 Handoff 數據保留期為 `30 days`。

## Open questions / conflicts
- [ ] **Arweave Archival**: 超過 90 天的關鍵教訓是否應在刪除前強制執行 `nexus:learning-sync` 上鏈。
- [ ] **Manual Lock**: 是否需要建立 `.lock` 標記以保護特定任務工件免於被 Pruning。

---
[[System Overview]]
