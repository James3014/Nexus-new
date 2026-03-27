# Nexus Phase 5 研究封版（2026-03-28）

## 1) 封版結論
- 本輪研究已完成，達成 Phase 5 驗收門檻。
- 驗收基線採用固定參數回歸（`PRECISION_ALPHA=0.99`，30 輪）。
- 結果：
  - `mismatch_lt_0.5_last20 = 20`
  - `mismatch_max_last20 = 0.374`
  - `proof_ratio_min_last20 = 98.88`
  - `best_precision = 0.99`
  - `global_converged = true`
  - `gate_pass_rate = 100.0`

## 2) 封版工件（Artifacts）
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase5_fixed_p099_round_summary.jsonl`
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase5_fixed_p099_gate_eval.json`
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase5_fixed_p099_param_state.json`

## 3) 工件指紋（SHA256）
- `3eff23bfd2a614db1e1f197eb611bb7752866638e4ed0aca0680d93d161d0022`  `phase5_fixed_p099_round_summary.jsonl`
- `572fe24c1a41c418148684236b13004e998b2ea2bccd0d31e8f6a0c8dfc6e048`  `phase5_fixed_p099_gate_eval.json`
- `d3ee7d44db0e6ffc0efdf901ce470f9ea699d5c8c83e763c9a9ad5542ca71287`  `phase5_fixed_p099_param_state.json`

## 4) 執行上下文
- Repo HEAD（封版時）：`151560a`
- 分支：`feat/v16.5-hybrid-singularity`
- 說明：倉庫目前為大量進行中變更狀態，本封版以「研究工件 + 指紋」作為可重現基準。

## 5) 封版準則
- 若後續研究未同時滿足以下條件，不可覆蓋本封版：
  - `proof_ratio_min_last20 >= 95.0`
  - `mismatch_lt_0.5_last20 = 20`
  - `global_converged = true`
  - `gate_pass_rate = 100.0`
