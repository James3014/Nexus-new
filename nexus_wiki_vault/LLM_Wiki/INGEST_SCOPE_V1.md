---
title: LLM_Wiki INGEST_SCOPE_V1
type: ops
status: active
version_scope: v1.0
owner: agent
confidence: high
last_compiled: 2026-04-21
source_of_truth: LLM_Wiki/INGEST_SCOPE_V1.md
tags:
  - llm-wiki
  - ingest
  - scope
---

# LLM_Wiki INGEST_SCOPE_V1
版本: v1.0
狀態: Draft for review（只定規則，不搬檔）
目標: 以三層處理策略建立可持續、可審核的 LLM Wiki ingest 範圍

## 1) 決策摘要
採用三層策略：
- Hard Exclude：永不 ingest
- Quarantine：只索引，不直接進主知識層
- Distilled Include：僅蒸餾後可公開重用知識可進主 wiki

## 2) Scope 定義
### 2.1 In-scope（候選）
- /Users/jameschen/Downloads/obsidian/知識庫（扣除排除與隔離規則後）

### 2.2 Hard Exclude（以 EXCLUDE_RULES.md 為準）
- 既定排除：Yang_Ding_Yi、Skiing
- 新增排除：Migration_Pack、FB_Scraping_Temp、Prompts
- 條件式排除：SOUL.md / TASK_STATE / SKILLS_REGISTRY / system prompt / sub-agent / credentials-token-session-webhook secret 類

### 2.3 Quarantine（先索引）
- 00_System_Knowledge/02_Arsenal/OpenClaw
- 00_System_Knowledge/02_Arsenal/AI_Agents/OpenClaw

### 2.4 Distilled Include（可入主 wiki）
僅接收以下蒸餾產物：
- 架構原理
- 故障模式
- 設計取捨
- 可驗證 SOP

## 3) 盤點基線（由既有掃描結果提供）
排除 Yang_Ding_Yi + Skiing 後：
- 總 md：1466
- openclaw 命名命中：241
- agent 命名命中：251
- brain 命名命中：29
- 內容關鍵詞命中（OpenClaw/SOUL/TASK_STATE 等）：542

高風險資料夾規模：
- 暫存/Migration_Pack：189
- FB_Scraping_Temp：33
- OpenClaw：79
- AI_Agents/OpenClaw：122
- Prompts：22

## 4) Ingest Gate（V1 強制）
任何文件進入主 wiki 前需全部滿足：
1. 不在 Hard Exclude 路徑
2. 非條件式排除命中檔
3. 無 restricted 敏感命中
4. 具來源證據（source path + 摘要方式）
5. 若來源來自 Quarantine，必須是蒸餾結果而非原文改寫

## 5) 產物與路徑（本次僅規則）
本次已落地：
- /Users/jameschen/workspace/nexus/nexus_wiki_vault/LLM_Wiki/EXCLUDE_RULES.md
- /Users/jameschen/workspace/nexus/nexus_wiki_vault/LLM_Wiki/INGEST_SCOPE_V1.md

本次不執行：
- 不搬移檔案
- 不重寫原始筆記
- 不啟動批次 ingest

## 6) 下一步（待你審核後才執行）
- 建立 LLM_Wiki/_meta/INGEST_QUEUE_PHASE_A.md（只列候選，不寫內容）
- 建立 LLM_Wiki/_meta/BATCH_A1_MANIFEST.md（平衡配額，不單一子樹偏斜）
- 先跑 restricted + denylist lint，產生第一版 lint 報告

## One-sentence summary
以三層處理（排除、隔離、蒸餾進入）定義 LLM_Wiki 的可持續 ingest 邊界。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Role / responsibility
- 管理 LLM_Wiki 來源收斂規則，避免非規範內容進入主知識庫。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]
- 保持可審核、可追蹤、可回溯的 ingest 範圍。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Upstream
- **[LLM_Wiki/EXCLUDE_RULES](EXCLUDE_RULES.md)**: 具體排除規則。 [Source: LLM_Wiki/EXCLUDE_RULES.md]
- **[Reference/Role_Guides/Expert_Guide](../Reference/Role_Guides/Expert_Guide.md)**: 人工審核規則對齊。 [Source: Reference/Role_Guides/Expert_Guide.md]

## Downstream
- **[LLM_Wiki/EXCLUDE_RULES](EXCLUDE_RULES.md)**: 同步變更後續門檻。 [Source: LLM_Wiki/EXCLUDE_RULES.md]
- **[06_Ops/Ops - Wiki Sync Check](../06_Ops/Ops - Wiki Page Type Contracts.md)**: 管理規則變更映射。 [Source: 06_Ops/Ops - Wiki Page Type Contracts.md]

## Related modules / files
- `LLM_Wiki/EXCLUDE_RULES.md`
- `scripts/ops/wiki_linter.py`
- `scripts/ops/wiki_coverage_audit.py`

## Source notes
- 入口規範依本頁與對應排除規則文件維護。 [Source: LLM_Wiki/INGEST_SCOPE_V1.md]

## Open questions / conflicts
- [ ] 是否要將 `workspace/obsidian` 的變更以增量而非全量方式同步？

**[Source: LLM_Wiki/INGEST_SCOPE_V1.md]**

[[System Overview]]
