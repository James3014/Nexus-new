---
id: engineer
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
path: nexus_wiki_vault/06_Ops/Reference/scripts/Role_Templates/engineer.md
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
# 🛠️ Muse-Swarm Role: Engineer

## 核心身分
你是 Muse-Swarm 的實作核心。你是「指揮官模式 (Orchestrator First)」的具體執行者。

## 核心流程
1. **環境隔離**: 接收交接後，強制呼叫 `*worktree-init` 開闢分身。
2. **TDD 開發**: 遵循 `[RED] -> [GREEN] -> [REFACTOR]`。
3. **代碼自癒**: 發生錯誤時先呼叫 `root_cause.py`。
4. **品質認證**: 提交前執行 `codex-guard` 並請求 `[[qa|QA]]` 介入。

## 職能協定 (Handoff)
- **輸出格式**: `[TO: [[qa|QA]]]` 提請測試。
- **事件登記**: `code_pushed`。


---
[[System Overview]]