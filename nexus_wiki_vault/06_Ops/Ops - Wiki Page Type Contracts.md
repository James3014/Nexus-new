---
confidence: high
last_compiled: 2026-04-06
owner: agent
source_of_truth: compiled-wiki
status: active
tags:
- ops
- wiki
- governance
- contract
title: Ops - Wiki Page Type Contracts
type: governance
version_scope:
- v23
---



# Ops - Wiki Page Type Contracts

## One-sentence summary
本文件定義 Nexus Wiki 的頁面類型契約，規定各類型頁面的必要欄位、章節結構與版本控制規範，以確保 Wiki 知識庫的結構化與可稽核性。 [Source: 00_Home/System Overview.md] [Code: ci_gate.py]

## Role / responsibility
- **定義標準**: 為不同用途的 Wiki 頁面提供統一的結構模板。 [Code: ci_gate.py]
- **自動稽核**: 作為 `wiki_linter.py` 與 `wiki_capability_coverage_audit.py` 的邏輯基準。
- **維護品質**: 確保所有知識條目皆具備來源追蹤 (Provenance) 與責任歸屬 (Owner)。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總體治理入口。
- **[[99_Schema/nexus_wiki_vault/99_Schema/AGENT_SCHEMA.md]]**: 定義代理操作與元數據基礎。

## Downstream
- **[[scripts/ops/wiki_linter.py]]**: 執行實體檔案的語法與結構檢查。
- **[[scripts/ops/wiki_capability_coverage_audit.py]]**: 執行領域能力覆蓋檢查。

## Related modules / files
- `nexus_wiki_vault/` (Root)
- `scripts/ops/wiki_linter.py`

## Wiki Page Types & Contracts

### 1. System (系統/入口)
- **用途**: 描述系統總體、拓撲或高層次導航。
- **必要 Frontmatter**: `type: [home](../00_Home/System Overview.md)` 或 `type: system`, `status`, `owner`, `version_scope`.
- **必要章節**: `## One-sentence summary`, `## Navigation`, `## Related modules / files`.

### 2. Concept (概念/原理)
- **用途**: 解釋核心理論、算法或架構設計（如 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]）。
- **必要 Frontmatter**: `type: concept`, `owner`, `source_of_truth`.
- **必要章節**: `## One-sentence summary`, `## Role / responsibility`, `## Source notes`.

### 3. Phase (相位/流程)
- **用途**: 詳述 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 或其他運作流程的特定階段。
- **必要 Frontmatter**: `type: phase`, `owner`.
- **必要章節**: `## One-sentence summary`, `## Flow details`, `## Input/Output`, `## Source notes`.

### 4. Command (指令/介面)
- **用途**: 記錄 CLI 指令、參數、風險等級與預期行為。
- **必要 Frontmatter**: `type: command`, `owner`, `risk_level`.
- **必要章節**: `## One-sentence summary`, `## Usage`, `## Source notes`.

### 5. Incident (事件/追查)
- **用途**: 記錄系統故障、RCA 過程與修復結果。
- **必要 Frontmatter**: `type: incident`, `status: closed/open`, `severity`.
- **必要章節**: `## One-sentence summary`, `## Root Cause Analysis`, `## Resolution`, `## Evidence`.

### 6. Decision (決策/ADR)
- **用途**: 記錄架構決策紀錄 (ADR) 與變更理由。
- **必要 Frontmatter**: `type: decision`, `status`, `owner`.
- **必要章節**: `## One-sentence summary`, `## Context`, `## Decision`, `## Consequences`.

## Required Frontmatter Fields (Global)
所有頁面必須包含：
- `owner`: 負責該頁面正確性的實體 (agent 或 human)。
- `status`: `active`, `deprecated`, 或 `draft`。
- `last_compiled`: YYYY-MM-DD 格式。
- `source_of_truth`: 標註原始來源（如 `compiled-wiki`, `spec-v22` 等）。

## Required Sections (Global)
所有頁面必須包含 `wiki_linter.py` 定義的七大章節：
1. `## One-sentence summary`
2. `## Role / responsibility`
3. `## Upstream`
4. `## Downstream`
5. `## Related modules / files`
6. `## Source notes`
7. `## Open questions / conflicts`

## Versioning Rules
- 所有 Wiki 頁面皆應標註 `version_scope` (如 `[v22, v23]`)。
- 涉及重大架構變更時，應建立新頁面或使用 `Diff` 頁面記錄差異。

## Source notes
- Nexus Wiki Governance v1.0
- Agent I Release Discipline

## Open questions / conflicts
- [ ] 是否應強制要求所有頁面皆具備 `[source:]` 或 `[code:]` 標籤（目前由 Linter 執行）。
- [ ] 針對 `type: incident` 的過期自動歸檔機制。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]