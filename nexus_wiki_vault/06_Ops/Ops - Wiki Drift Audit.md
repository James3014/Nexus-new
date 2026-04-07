---
aliases: '[Drift Audit, Wiki Drift, Stale [[documentation|Documentation]] Check]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/wiki_drift_audit.py
status: active
tags: '[ops, audit, drift, maintenance]'
title: Ops - Wiki Drift Audit
type: ops
version_scope: '[v17.1, v22, v23]'
---



# Ops - Wiki Drift Audit

## One-sentence summary
本頁解釋 Nexus Wiki 的「路徑脫節與時效漂移」自動審計機制。 [Source: scripts/ops/wiki_drift_audit.py]

## Role / responsibility
- **物理存在校驗**: 自動檢測 Wiki 內所有 `[Source: 00_Home/System Overview.md]` 提及的路徑在 Repo 中是否依然存在。 [Source: scripts/ops/wiki_drift_audit.py]
- **內容時效監控 (Stale Detection)**: 對比 Wiki 頁面的最後修改時間與其引用之程式檔案的 Git 最後提交時間。 [Source: scripts/ops/wiki_drift_audit.py]

## Drift Audit Mechanism (審計機制)

### 1. 物理掃描 (Physical Path Check)
- **邏輯**: 提取全庫 `[Source: 00_Home/System Overview.md]` 標籤 -> 對比 `PROJECT_ROOT` -> 若路徑不存在則記錄為 `Missing Claim`。
- **CI 整合**: 整合於 `ci_gate.py` 之 `Wiki Drift Audit` 步驟。 [Source: scripts/ops/ci_gate.py]

## Upstream
- **Wiki Audit Engine**: `scripts/ops/wiki_drift_audit.py` [Code: scripts/ops/wiki_drift_audit.py]

## Downstream
- **[Ops - Governance Changelog](Ops - Governance Changelog.md)**: 記錄漂移修復的歷史。

## Related modules / files
- `scripts/ops/wiki_drift_audit.py`: 漂移審計核心。 [Source: scripts/ops/wiki_drift_audit.py]

## Source notes
- v22 Engine Spec: 要求治理文檔必須具備「物理可對位性」與「時效一致性」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Hard Fail**: 何時將 Wiki Drift Audit 升級為 Hard Fail。

---
[System Overview](../00_Home/System Overview.md)
