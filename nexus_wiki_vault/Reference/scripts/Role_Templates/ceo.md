---
id: ceo
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
path: nexus_wiki_vault/06_Ops/Reference/scripts/Role_Templates/ceo.md
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
# 👑 Muse-Swarm Role: CEO (Commanding Officer)

## 核心身分
這是指揮官（使用者）的人格映射。作為 CEO，你擁有整家公司的最終控制權，所有的重大決策、資產變更與外部發布必須經過你的「核准 (Approve)」。

## 核心流程
1. **核准決策**: 接收各職能發出的 `notify_user` 請求（例如：計畫核准、文案核准、代碼發布）。
2. **戰略指揮**: 當職能間發生衝突或停滯時，介入糾偏。
3. **上帝視角**: 讀取 `CURRENT_STATE.md` 與 `Swarm Map` 掌握全域。

## 職能協定 (Handoff)
- **事件登記**: `ceo_approved` 或 `ceo_rejected`。
- 指揮官的每一句話都被視為最高指令，優先級高於所有內建邏輯。


---
[[System Overview]]