---
id: skill
type: doc
status: active
created: 2026-04-07T07:29:39Z
updated: 2026-04-07T07:29:39Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/scripts/nexus-planner-expert/SKILL.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Nexus Planner Expert Skill (Superpowers v5 Adapter)

## 描述
- 封裝 `obra/superpowers` v5 的 `[[writing-plans]]` 職能。
- 專注於高複雜度任務的「原子化計畫撰寫」。
- 強制執行「經驗回查協議」，確保在動工前已吸收過去的失敗教訓。

## 指令
- **經驗回查**: 強制調用 `qmd search` 檢索 `auto-skill` 經驗庫。
- **計畫撰寫**: 產出具備 TDD 驅動、頻繁提交 (Frequent Commits) 與預期結果的詳細實施計畫。
- **計畫審查**: 引導 Agent 進行計畫的自我稽核，確保路徑最優。

## 輸入合約
- **task_requirements**: 詳細的需求說明或規格書 (str)。
- **relevant_experience**: 預先檢索到的經驗片段 (str, 選填)。

## 輸出合約
- **[[implementation_plan]]**: 符合 Nexus v7+ 標準的原子化計畫文件 (str)。
- **recall_summary**: 過去相似任務的回查總結 (str)。

## 執行細節
- 本技能代理 `~/.gemini/skills/superpowers/[[writing-plans]]`。
- 始終遵循「不見計畫，不動代碼」的工程紀律。


---
[[System Overview]]