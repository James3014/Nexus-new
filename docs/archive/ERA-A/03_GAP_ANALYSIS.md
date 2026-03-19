# Muse-Nexus Gap Analysis

## Summary

現況與目標架構之間最大的差距，不在於能力完全缺失，而在於：

- 缺少明確 contract
- 缺少明確 phase ownership
- 缺少獨立 orchestration layer

## Gap Table

| Area | Current | Target | Gap |
| --- | --- | --- | --- |
| Orchestrator | `codex_loop_brain.py` 承擔多職責 | Commander 單一 orchestration layer | 需要拆責任並抽成正式入口 |
| Context assembly | 散落在 loop 腳本裡 | Context Hub 統一打包 | 需要獨立模組與 phase packs |
| State | 事件、session、markdown 摘要混用 | `.muse_state` + JSON contracts | 需要標準檔案與 schema |
| Diagnosis | ad hoc 結果 | `diagnosis.json` contract | 需要穩定 schema |
| Repair | patch loop 已存在 | round-based Repair engine | 需要 round records 與 final contract |
| Audit | 多個 audit 腳本 | 統一 Audit engine | 需要合併 deterministic gates 與 verdict output |
| Crystal | memory ingest 強 | 任務導向 lesson pipeline | 需要與 task workflow 收斂 |
| External research | 幾乎未落地 | X phase + `research_pack.json` | 需要明確 gating 與輸出 |
| Skills routing | 沒有 | 表驅動 skills router | 需要 routing table 與 output contracts |
| Project docs | 幾乎沒有 | repo 內文件化管理 | 本次已開始補齊 |

## Reality Check

下面這些能力已經足夠支持演進，不需要重寫：

- git / worktree isolation
- memory retrieval
- ingest / crystallization
- diagnosis 前身
- audit 前身

真正應該重構的，是：

- orchestration 邊界
- state 管理方式
- 模組責任分離

## Practical Interpretation

這表示 Muse-Nexus 不是從零開始，而是：

```text
existing scripts + memory engine + git isolation
    -> add contracts
    -> extract context hub
    -> add commander
    -> add router
```

這條路線的風險比大翻修低很多。
