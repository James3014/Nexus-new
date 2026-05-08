---
title: LLM_Wiki EXCLUDE_RULES
type: ops
status: active
version_scope: v1.0
owner: agent
confidence: high
last_compiled: 2026-04-21
source_of_truth: LLM_Wiki/EXCLUDE_RULES.md
tags:
  - llm-wiki
  - exclude
  - scope-control
---

# LLM_Wiki EXCLUDE_RULES
版本: v1.0
狀態: Draft for review
適用範圍: /Users/jameschen/Downloads/obsidian/知識庫
原則: 三層處理（Hard Exclude / Quarantine / Distilled Include）

## A. Hard Exclude（禁止進入 LLM_Wiki ingest）

### A1. 既定排除路徑（絕對路徑）
- /Users/jameschen/Downloads/obsidian/知識庫/04_Life_OS/Yang_Ding_Yi
- /Users/jameschen/Downloads/obsidian/知識庫/Skiing

### A2. 新增排除路徑（agent 腦內/暫存/原始抓取）
- /Users/jameschen/Downloads/obsidian/知識庫/暫存/Migration_Pack
- /Users/jameschen/Downloads/obsidian/知識庫/05_External_Infusion/Raw_Sources/FB_Scraping_Temp
- /Users/jameschen/Downloads/obsidian/知識庫/00_System_Knowledge/02_Arsenal/Prompts

### A3. 條件式排除（不論所在資料夾）
任一檔案若符合以下任一條件，直接 Hard Exclude：

1) 檔名命中（不分大小寫）
- SOUL.md
- TASK_STATE
- SKILLS_REGISTRY

2) 內容命中（不分大小寫）
- system prompt
- sub-agent

3) 敏感資訊命中（不分大小寫，命中即標記 restricted 並排除）
- credentials
- token
- session
- webhook secret
- api key
- private key

## B. Quarantine（先不入主知識層，只建立索引/清單）
- /Users/jameschen/Downloads/obsidian/知識庫/00_System_Knowledge/02_Arsenal/OpenClaw
- /Users/jameschen/Downloads/obsidian/知識庫/00_System_Knowledge/02_Arsenal/AI_Agents/OpenClaw

處理規則：
- 允許做檔名級索引、主題標籤、路徑統計。
- 不做原文搬運，不做逐段重寫到主 wiki。
- 只允許輸出可公開重用的「蒸餾摘要」到 Distilled Include。

## C. Distilled Include（可進主 wiki）
僅允許以下內容型別：
- 架構原理
- 故障模式
- 設計取捨
- 可驗證 SOP（可用步驟+驗證條件）

禁止帶入：
- 私有 prompt 原文
- 身份設定/人格設定原文
- 密鑰路徑或憑證資訊
- 個人化行為協議原文

## D. Pre-Ingest Gate（入庫前檢查）
每批次入庫前必須同時通過：
1) Path denylist：路徑不在 A1/A2/B 清單（B 僅允許蒸餾產物）
2) Filename denylist：不得命中 A3(1)
3) Content denylist：不得命中 A3(2)
4) Restricted scan：不得命中 A3(3)
5) Provenance：每篇蒸餾頁面需可回溯來源路徑（不含敏感原文）

## E. 實作建議（供程式化掃描）
- 路徑比對: normalize absolute path 後比對前綴。
- 字串比對: case-insensitive。
- 建議正則（示意）：
  - (?i)\b(SOUL\.md|TASK_STATE|SKILLS_REGISTRY)\b
  - (?i)\b(system\s*prompt|sub-agent)\b
  - (?i)\b(credentials?|token|session|webhook\s*secret|api\s*key|private\s*key)\b

## F. 變更控制
- 本文件任何變更需先審核，不直接重跑全量 ingest。
- 先更新 INGEST_SCOPE_V1.md 的「影響範圍」再執行。

## One-sentence summary
定義 LLM_Wiki ingest 的排除、隔離與蒸餾納入條件，防止高風險原文直接進主知識層。 [Source: LLM_Wiki/EXCLUDE_RULES.md]

## Role / responsibility
- 提供硬性過濾規則，降低敏感或無關資訊污染。 [Source: LLM_Wiki/EXCLUDE_RULES.md]
- 引導蒸餾流程，保留可公開與可驗證內容。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Upstream
- **[LLM_Wiki/INGEST_SCOPE_V1](INGEST_SCOPE_V1.md)**: 進一步定義納入邊界。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Downstream
- **[wiki_linter](../scripts/ops/wiki_linter.py)**: 門檻與可追蹤性驗證。 [Source: scripts/ops/wiki_linter.py]
- **LLM_Wiki INGEST_PIPELINE**: 待建立的批次 ingest 計畫。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Related modules / files
- `LLM_Wiki/INGEST_SCOPE_V1.md`
- `scripts/ops/wiki_linter.py`
- `scripts/ops/wiki_coverage_audit.py`

## Source notes
- 規則基於現有工作流程與敏感資料風險清單維護。 [Source: LLM_Wiki/EXCLUDE_RULES.md]

## Open questions / conflicts
- [ ] 是否要納入 API token 格式變化的動態規則更新？

**[Source: LLM_Wiki/EXCLUDE_RULES.md]**

[[System Overview]]
