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
path: nexus_wiki_vault/06_Ops/Reference/scripts/nexus-debug-expert/SKILL.md
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
# Nexus Debug Expert Skill (Superpowers v5 Adapter)

## 描述
- 封裝 `obra/superpowers` v5 的 `systematic-debugging` 職能。
- 執行嚴格的「四階段根因分析法」：重現 -> 定位 -> 修復 -> 驗證。
- 用於解決複雜系統中的連鎖錯誤，嚴禁「盲目修補」。

## 指令
- **根因分析**: 引導 Agent 執行動態探針、日誌分析與環境比對。
- **防禦性修復**: 產出具備自癒能力的修復計畫。
- **自動結晶**: 修復成功後，強制調用 `auto-skill` 寫回經驗庫。

## 輸入合約
- **error_context**: 錯誤訊息、堆棧追蹤或失敗的測試結果 (str)。
- **relevant_files**: 可能相關的原始碼檔案清單 (list[str])。

## 輸出合約
- **root_cause_analysis**: 深度根因分析報告 (str)。
- **fix_implementation_plan**: 分步驟的修復實施計畫 (str)。
- **prevention_strategy**: 長期防禦建議，避免同類 Bug 再現 (str)。

## 執行細節
- 本技能代理 `~/.gemini/skills/superpowers/systematic-debugging`。
- 始終遵循「不見根因，絕不動手」的最高紀律。


---
[[System Overview]]