---
id: 07_script_ownership_map
type: doc
status: active
created: 2026-04-07T07:29:30Z
updated: 2026-04-07T07:29:30Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/07_SCRIPT_OWNERSHIP_MAP.md
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
# Muse-Nexus Script Ownership Map

## Goal

這份文件用來回答三個問題：

1. 哪些腳本目前看起來是現役主幹。
2. 哪些 root-level scripts 與 `scripts/core/` 存在重複。
3. 後續整理時，哪些檔案應視為 canonical、wrapper、或 deprecated candidate。

## Current Rule

在正式收斂前，先採用這個暫行判定：

- `scripts/` root-level orchestration scripts：視為現役入口層
- `scripts/core/`：視為被部分現役入口依賴的 library layer
- `scripts/_migrated_from_obsidian/`：視為 historical snapshot

## Confirmed Runtime Relationship

目前已確認：

- `scripts/codex_loop_brain.py` 直接 import：
  - `core.git_manager`
  - `core.llm_client`
  - `core.linter`
  - `core.patcher`
  - `core.reporter`
  - `core.workspace_manager`

這表示：

- `scripts/core/` 不是單純備份
- `codex_loop_brain.py` 是現役入口之一
- root-level 與 `core/` 已形成「入口層 -> library layer」的部分架構

## Ownership Categories

### Category A: Current Entry Points

這些檔案目前應優先視為現役入口或現役操作腳本：

- `scripts/codex_loop_brain.py`
- `scripts/workspace_manager.py`
- `scripts/git_manager.py`
- `scripts/drclaw_diagnosis.py`
- `scripts/brain_search_v2.py`
- `scripts/brain_search_v3.py`
- `scripts/brain_search_v4.py`
- `scripts/flash_ingest_v2.py`
- `scripts/pre_write_quality_gate.py`
- `scripts/app.py`
- `scripts/script_dashboard.py`

### Category B: Active Library Candidates

這些 `scripts/core/` 檔案目前已明確被主幹使用，應視為 active library candidates：

- `scripts/core/git_manager.py`
- `scripts/core/llm_client.py`
- `scripts/core/linter.py`
- `scripts/core/patcher.py`
- `scripts/core/reporter.py`
- `scripts/core/workspace_manager.py`

### Category C: Historical Snapshot

這一整區先視為 historical / archive candidate：

- `scripts/_migrated_from_obsidian/01_Operations/scripts/*`

## Duplicate Filename Map

下列檔名同時存在於 root-level `scripts/` 與 `scripts/core/`：

- `brain_b_health_monitor.py`
- `brain_b_incubator.py`
- `brain_b_indexer.py`
- `brain_b_reality_check.py`
- `brain_search_v3.py`
- `drclaw_diagnosis.py`
- `git_manager.py`
- `guard_executor.py`
- `idea_decomposer.py`
- `linter.py`
- `llm_client.py`
- `parallel_spawner.py`
- `patcher.py`
- `reality_check_v2.py`
- `reporter.py`
- `self_evolution.py`
- `semantic_gravity_smelter.py`
- `steward.py`
- `trigger_test.py`
- `workspace_manager.py`

## Initial Ownership Decision

這裡不是最終結論，而是目前最安全的暫行策略。

### 1. Files likely to become `core/` canonical

理由：

- 已被 `codex_loop_brain.py` 直接 import
- 角色偏通用能力，不像 CLI/entrypoint

Suggested canonical side:

- `git_manager.py`
- `linter.py`
- `llm_client.py`
- `patcher.py`
- `reporter.py`
- `workspace_manager.py`

暫行策略：

- 優先把 `scripts/core/*.py` 視為 library canonical
- root-level 同名檔案視為待確認 duplicate
- 已執行 (2026-03-14): 將 root-level 同名檔案 (`git_manager.py`, `workspace_manager.py`, `linter.py`, `patcher.py`, `llm_client.py`, `reporter.py`) 遷移至 `scripts/legacy/`。

### 2. Files likely to remain root-level entrypoints

理由：

- 角色偏操作入口、任務入口、流程入口

Suggested canonical side:

- `codex_loop_brain.py`
- `brain_search_v2.py`
- `brain_search_v4.py`
- `flash_ingest_v2.py`
- `pre_write_quality_gate.py`
- `app.py`
- `script_dashboard.py`

### 3. Files requiring explicit review before any move

這些有 duplicate，但目前沒有足夠證據直接判定誰是 canonical：

- `brain_b_health_monitor.py`
- `brain_b_incubator.py`
- `brain_b_indexer.py`
- `brain_b_reality_check.py`
- `brain_search_v3.py`
- `drclaw_diagnosis.py`
- `guard_executor.py`
- `idea_decomposer.py`
- `parallel_spawner.py`
- `reality_check_v2.py`
- `self_evolution.py`
- `semantic_gravity_smelter.py`
- `steward.py`
- `trigger_test.py`

這一組應在後續逐檔確認：

- 誰被 import
- 誰被 shell / cron / dashboard 直接呼叫
- 哪個版本更新較新
- 哪個版本包含實際有效行為

## Practical Ownership Rule

在沒有完成逐檔盤點前，先採用以下規則：

```text
root-level scripts = current operational entrypoints
scripts/core = reusable library candidates
_migrated_from_obsidian = historical snapshot
```

這個規則的好處是：

- 不需要立刻搬檔
- 不會先誤刪現役入口
- 可以讓後續 Commander / [[Module - Intelligence and Context Core|Context Hub]] 重構有清楚落點

## Next Actions

- [ ] 為 duplicate pairs 補充「誰引用誰」資訊
- [ ] 檢查 dashboard / shell scripts / cron 是否直接呼叫 root-level duplicates
- [ ] 為每個 duplicate pair 決定：
  - canonical
  - wrapper
  - deprecated candidate
- [ ] 為 historical snapshot 補上 deprecation note
- [ ] 規劃一次單獨的 duplicate cleanup 任務

## Practical Conclusion

Muse-Nexus 現在最大的 ownership 問題不是「不知道有哪些腳本」，而是：

> 同名腳本同時存在於入口層與 library layer，卻還沒有正式宣告誰才是 canonical。

這份文件先把這件事攤開，讓後續整理可以在明確 ownership 下進行，而不是邊猜邊搬。


---
[[System Overview]]