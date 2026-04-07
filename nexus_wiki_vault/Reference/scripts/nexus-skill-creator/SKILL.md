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
path: nexus_wiki_vault/06_Ops/Reference/scripts/nexus-skill-creator/SKILL.md
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
# Nexus Skill Creator (Eval & Optimization Adapter)

## 描述
- 封裝 `obra/skill-creator` 職能。
- 專注於 Nexus 內部技能的「建立、強化、修復與评量 (Eval)」。
- 用於解決技能「觸發不準確」或「生成結果偏移」的問題，實現職能庫的自我進化。

## 指令
- **技能建立**: 引導用戶定義新職能的 Intent、Triggers 與合約。
- **技能強化**: 基於 `feedback.json` 對現有技能進行迭代優化。
- **技能修復**: 當偵測到技能執行失敗時，執行自動化 Debug 與 Eval 驗證。
- **評量觀測**: 啟動 `eval-viewer/generate_review.py` 提供定性與定量的數據報告。

## 輸入合約
- **skill_id**: 待優化或建立的技能 ID (str)。
- **test_prompts**: 用於 Eval 的測試案例清單 (list[str])。
- **user_feedback**: 針對現有輸出的修正意見 (str, 選填)。

## 輸出合約
- **best_description**: 經優化後的技能觸發描述 (str)。
- **eval_report**: 包含通率、耗時與 Token 消耗的 Benchmark 報告 (str/JSON)。
- **updated_skill_file**: 修改後的 `SKILL.md` 內容 (str)。

## 執行細節
- 本技能代理 `~/.agents/skills/skill-creator/` 核心邏輯。
- 所有評量與迭代過程必須公開透明，並產出視訊或報告證據。


---
[[System Overview]]