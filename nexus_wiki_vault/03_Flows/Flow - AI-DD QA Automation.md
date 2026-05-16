---
title: Flow - AI-DD QA Automation
aliases: [AI-DD QA, Q42 Quality Framework]
type: flow
status: active
version_scope: [v26]
source_of_truth: docs/plans/NEXUS_LEARNING_SYNC_MASTER.md
tags: [qa, automation, playwright, ai-dd]
last_compiled: 2026-05-17
---

# Flow - AI-DD QA Automation (Q42 品質框架)

## One-sentence summary
本流程描述如何將產品需求 (PRD) 自動轉化為具備 16 條自我審查機制的核心 Playwright UI 測試案例。 [Source: docs/plans/NEXUS_LEARNING_SYNC_MASTER.md]

## 🏗️ 核心架構 (The Framework)

AI-DD (AI-Driven Development) 質量框架將測試左移至需求階段，實現「需求即測試」的自動化閉環。

### 1. 結構化 GWT 撰寫
- **Given**: 定義初始狀態與環境（如租戶登入狀態）。
- **When**: **單一 DOM 互動限制**。每個 When 步驟僅能對應一個精確動作（點擊、輸入）。
- **Then**: 斷言預期結果，優先引用 Skill Labels。

### 2. AI 自我審查 (Self-Review Checklist)
產出後強制執行 16 條校驗規則：
- **無模糊詞**: 嚴禁使用「可能」、「大約」等詞彙。
- **DOM 唯一性**: 驗證互動對象具備唯一的 `data-testid` 或語義路徑。
- **異常路徑覆蓋**: 至少包含 1 個邊界條件或錯誤處理案例。

## ⚙️ 執行序列 (Execution Sequence)

1. **Scan**: AI 讀取 `nexus_wiki_vault/00_Product/User Stories.md`。
2. **Translate**: 將自然語言轉化為 Python/TypeScript Playwright 腳本。
3. **Audit**: 執行 16 條 Checklist 校驗。
4. **Link**: 與 DevOps 平台（如 GitHub Actions）建立 `Test Goal` 關聯。

## Role / responsibility
- 確保測試工件與需求規格 1:1 對位。
- 提供可量化的「需求涵蓋率」指標。

## Upstream
- **[[00_Product/User Stories]]**: 提供原始需求。
- **[[01_System/ADR/ADR-2026-05-06-audit-cli-and-event-strict-lessons]]**: 提供審計規範。

## Downstream
- **[[06_Ops/Ops - Performance Benchmarks]]**: 測試腳本可作為性能壓測的基礎。

## Related modules / files
- `scripts/qa/ai_dd_generator.py`: AI-DD 腳本生成器。
- `tests/qa/test_q42_framework.py`: 框架自驗證測試。

## Source notes
- 源於 91APP 提出的 Q42 品質框架，已於 2026-05-17 正式整合至 Nexus 演化知識庫。

---
[[System Overview]]
