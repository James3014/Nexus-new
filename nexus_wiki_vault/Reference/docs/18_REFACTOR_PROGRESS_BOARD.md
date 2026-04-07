---
id: 18_refactor_progress_board
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
path: nexus_wiki_vault/06_Ops/Reference/docs/18_REFACTOR_PROGRESS_BOARD.md
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
# Refactor Progress Board

Last Updated: 2026-03-17

## Snapshot

Status legend:
- DONE
- IN_PROGRESS
- TODO

## Current Runtime

```text
nexus_cli.py
  -> NexusEngine (P/X/D/R/A/C)
    -> ContextHub / StateIO / Reviewer / Router
      -> .musestate + .nexus_metrics + benchmark JSON
```

## Done

- [DONE] diagnostics 分軌：`stable` / `legacy-all`
- [DONE] legacy diagnostics 相容修復（adapter + reviewer [[compatibility]]）
- [DONE] benchmark score hardening（flow/execution/quality）
- [DONE] benchmark schema versioned output
- [DONE] simulated_run / simulation_reasons / last_review_status signals
- [DONE] parallel state/metrics isolation stress script + passing baseline
- [DONE] [[Module - Memory Repository|LanceDB]] table listing [[compatibility]] helper (`list_tables` fallback)
- [DONE] [[task]] Router（Nexus vs Direct）決策框架
- [DONE] `nexus-cli` 輕量命令啟動優化（warroom 不依賴重引擎導入）
- [DONE] CI workflow 改為 matrix 三 lane（unit / diagnostics-stable / stress-quick）
- [DONE] nightly 趨勢 workflow（stress report + prometheus snapshot artifact）
- [DONE] `run_feature` [[Module - Intelligence and Context Core|context hub]] 相容 fallback（缺 `assemble_feature_pack` 不再直接 crash）
- [DONE] `run_feature` [[Module - Intelligence and Context Core|context hub]] 相容 fallback 強化（`assemble_feature_pack` 拋錯時也自動降級，不中斷流程）

## In Progress

- [DONE] 核心模組 print -> logger 收斂（主執行鏈 + 主要 utility 已完成）
- [IN_PROGRESS] nightly 趨勢 workflow + observability 對接（長時序 dashboard 尚待固定）

## TODO

- [TODO] `scripts/` 現役/歷史導覽分層與去噪
- [TODO] docs lint（索引有效性 + Last Updated 檢查）
- [TODO] benchmark 結果差異比較工具（run vs run）
- [TODO] 長時序 Prometheus/Grafana 看板固定化

## Acceptance Gate (Current)

1. `pytest` 綠燈
2. `run_diagnostics.py --profile stable` 綠燈
3. `run_diagnostics.py --profile legacy-all` 綠燈
4. stress quick lane 綠燈
5. benchmark JSON schema 符合 docs/21


---
[[System Overview]]