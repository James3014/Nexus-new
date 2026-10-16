# Muse-Nexus Execution Timeline

## Purpose

這份文件把目前的 migration 規劃整理成可執行的 4 週節奏，讓 agent 與人類知道：

- 每週優先目標
- 誰主導
- 驗證標準
- 何時可以往下一階段推進

## High-Level Goal

- 維持 P-D-X-R-A-C 流程
- 維持 JSON 權威 state
- 先 internal path
- 以全域 validator 做 phase gatekeeper
- internal-only path token / latency overhead 目標小於舊版基準 `1.2x`
- legacy tasks best-effort compatibility，不可 crash

## Week 1

### Focus

- baseline freeze
- migration safety validator prototype
- repo / state baseline clarification

### Main tasks

- 實作 `scripts/core/migration_safety_validator.py` prototype
- 支援：
  - `--mode gatekeeper`
  - `--mode half-upgrade`
- 建立 baseline:
  - current commit SHA
  - smoke command
  - sample `.muse_state`
  - internal-only token / latency baseline

### Ownership

- agent 起草
- human review validator semantics / gate conditions

### Exit criteria

- gatekeeper mode 可執行
- half-upgraded state 至少 2 個案例可模擬
- baseline 已凍結

## Week 2

### Focus

- state contracts
- state IO
- skills router skeleton

### Main tasks

- 建立 `state_contracts.py`
- 建立 `state_io.py`
- 建立 `skills_router.py` skeleton
- 建立 sample routing cases
- 建立 scorecard prototype

### Suggested router target

- top-1 correctness 先以 `> 80%` 為 prototype 目標
- `stacktrace_match > 0.8` 視為 D phase strong signal prototype

### Ownership

- agent 主做
- human review:
  - schema naming
  - router scoring logic

### Exit criteria

- contract 欄位與文件一致
- router 可輸出 reason / score / threshold
- sample cases 可跑

## Week 3

### Focus

- Context Hub
- repair integration
- minimal D/R path

### Main tasks

- 建立 `context_hub.py`
- 建立 `reflection_store.py`
- 讓 repair path 讀 `repair_context_pack`
- 讓 repair path 寫 reflection
- 讓 diag path 輸出結構化 diagnosis / `needs_research`

### Validation

- 端到端 smoke path:
  - import
  - contract read/write
  - context assembly
  - repair loop minimal path
- internal-only token / latency 對照 baseline

### Ownership

- agent + human 混合
- human 強審 repair loop 改動

### Exit criteria

- smoke path 可通
- half-upgraded state 不 crash
- internal-only overhead 未明顯失控

## Week 4

### Focus

- external routing
- full acceptance
- legacy compatibility pass

### Main tasks

- 接 `research_pack.json`
- external routing fallback
- acceptance checklist 全跑
- legacy task compatibility pass

### Ownership

- human 主導
- agent 協助實作與修補

### Exit criteria

- external fallback 正常
- acceptance checklist 達標
- legacy tasks best-effort compatibility confirmed

## Gating Rules

每週若未達 exit criteria，不應進下一週主題。

尤其：

- Week 1 gatekeeper 未穩定，不進 Week 2
- Week 2 contracts / router 未穩定，不進 Week 3 repair integration
- Week 3 smoke path 未通，不進 Week 4 external routing

## Practical Conclusion

這份時間表的核心不是排滿工作，而是：

> 先建立守門能力與量化基準，再讓新架構逐步接管舊系統。
