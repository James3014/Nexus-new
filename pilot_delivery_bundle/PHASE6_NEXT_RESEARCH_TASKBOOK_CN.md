# Nexus Phase 6 研究任務書（給下一位 Agent）

## 任務目標
在不破壞 Phase 5 封版基線的前提下，提升「證據鏈穩定性 + 精準度可持續性」，並產出可比較的 time-series 證據。

## Hard Gate（必須全部通過）
- `proof_ratio_min_last20 >= 95.0`
- `mismatch_lt_0.5_last20 = 20`
- `global_converged = true`
- `gate_pass_rate >= 95.0`（若跑長輪次，允許少量探索失敗）

## 研究範圍（只允許）
- `Autoresearch/train.py`
- `Autoresearch/autopilot.py`
- `Autoresearch/formal_research_hardening.py`
- 輸出工件目錄（不得覆蓋 Phase 5 封版檔案）

## 建議研究題目（按順序）
1. **RCA 收斂品質**
- 將 `preflight_missing_proof`、`preflight_invalid_proof`、`proof_mismatch` 做分層採樣統計。
- 目標：把前兩項佔比壓到總 fail 的 80% 以下，避免單一失敗型態壟斷。

2. **門檻動態策略**
- 比較固定 95% vs 分段 90->95 的長輪次穩定度差異。
- 輸出：至少 3 組對照 run 的 `gate_eval.json`。

3. **Precision 阻尼優化**
- 維持單變量主路徑（優先調 `PRECISION_ALPHA`），新增抗震盪策略（例如雙窗口確認再步進）。
- 目標：降低 `mismatch_max_last20` 的尾部波動。

## 交付物（不可缺）
- `phase6_round_summary.jsonl`
- `phase6_gate_eval.json`
- `phase6_param_state.json`
- `phase6_research_report_cn.md`（需包含：
  - 實驗矩陣
  - 最佳參數
  - 失敗分桶 Top 5
  - 與 Phase 5 基線比較）

## 驗收指令（最小集）
```bash
python3 autopilot.py
python3 formal_research_hardening.py \
  --input phase6_round_summary.jsonl \
  --out phase6_out \
  --proof-ratio-min 95.0
```

## 禁止事項
- 不得宣稱通過但缺少 `gate_eval.json`。
- 不得只報最佳單輪，必須報 last20 指標。
- 不得覆蓋 `/Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch/phase5_fixed_p099_*` 封版檔案。
