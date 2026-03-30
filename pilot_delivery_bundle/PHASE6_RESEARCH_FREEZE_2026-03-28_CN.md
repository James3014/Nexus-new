# Nexus Phase 6 研究封版（2026-03-28）

## 1) 封版結論
- 本輪 Phase 6 已完成，且通過 hard gate。
- 研究執行方式：`nexus:phase6`（使用 `proof_ratio_min=95`，本次以現有 round_summary 做 hardening 與報告重算）。
- 結果：
  - `mismatch_lt_0.5_last20 = 20`
  - `mismatch_max_last20 = 0.368`
  - `proof_ratio_min_last20 = 98.44`
  - `best_precision = 0.99`
  - `global_converged = true`
  - `gate_pass_rate = 100.0`

## 2) 封版工件（Artifacts）
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase6_out/round_summary.jsonl`
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase6_out/gate_eval.json`
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase6_out/param_state.json`
- `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase6_research_report_cn.json`

## 3) 工件指紋（SHA256）
- `ff00adf15dc150d3d34f361ed126e814f800d1bde58dfb267d0393600c870bbf`  `phase6_out/round_summary.jsonl`
- `e127af3fa68d26b1fcb8601a3fef4c08d3656cdb210b7d79adc34f9346342bb0`  `phase6_out/gate_eval.json`
- `1f7bff2ab75b26632a4a46055cea47f842c87dc32bd6a16083c47f64f8d1f02d`  `phase6_out/param_state.json`
- `c28d8d029be3f5aadec50d38ecb9c5de8c9171a12bb78421f2e1b5d76fe0b666`  `phase6_research_report_cn.json`

## 4) 執行上下文
- Repo HEAD（封版時）：`5909dd5`
- 分支：`feat/v16.5-hybrid-singularity`

## 5) 封版準則
- 後續研究若未同時滿足以下條件，不可覆蓋本封版：
  - `proof_ratio_min_last20 >= 95.0`
  - `mismatch_lt_0.5_last20 = 20`
  - `global_converged = true`
  - `gate_pass_rate >= 95.0`
