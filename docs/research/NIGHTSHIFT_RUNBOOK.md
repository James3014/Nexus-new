# 🌙 NightShift Runbook (P7 Production-Ready)

## 🎯 觸發條件 (Trigger Criteria)
- **Local Convergence**: 當 Hyper-Sprint 產出多個候選補丁，需在本地環境進行壓力測試與收斂。
- **Batch Processing**: 離線執行大規模 A/B 基準測試或 NAS 自動調參。
- **High-Stakes Recovery**: 針對 P0 級別的歷史教訓回灌與驗證。

## 🛠️ 參數模板 (Parameter Templates)

### 1. 本地收斂測試 (Convergence Run)
```bash
uv run scripts/nightshift.py \
  --task "auth-timeout-fix" \
  --max_rounds 3 \
  --target_file "nexus/services/auth.py"
```

### 2. 批量 A/B 驗證 (Batch AB)
```bash
uv run scripts/engine/nexus_cli.py nexus research:benchmark \
  --manifest-file docs/research/research_benchmark_ab_10cases_mixed.json \
  --mode ab \
  --ab-trials 3
```

## 🚨 故障處理 (Troubleshooting)

| 症狀 (Symptom) | 可能原因 | 處置行動 (Action) |
| :--- | :--- | :--- |
| `stale_lock` | 前次任務異常中斷 | 檢查 `.nexus/locks/`，手動刪除過期 PID 檔案。 |
| `divergence` | 權重過於激進 | 調整 `autonomic_weights.json` 中的 `exploration_ratio`。 |
| `no_checkpoint` | 磁碟空間不足 | 執行 `nexus:clean` 釋放 `.nexus/runs/` 空間。 |

## ✅ DoD (Definition of Done)
- [ ] 完成 P1~P4 的收斂報表輸出。
- [ ] 學習成果成功寫入 `policy_memory.jsonl`。
- [ ] 通過 `ci_gate.py --dry-run` 檢核。

## 🧪 Meta-Optimization Mode
Run preset search to tune NightShift-compatible benchmark parameters safely.

```bash
uv run scripts/engine/nexus_cli.py nexus research:meta-opt \
  --manifest-file docs/research/research_benchmark_ab_rate_limiter_only.json \
  --presets-file docs/research/research_meta_presets_smoke.json \
  --max-wall-time-sec 120 \
  --report-file .nexus/reports/research/meta-opt-r13-smoke.json
```

Expected output:
- machine-readable ranking of presets
- selected preset under fail-closed policy
- partial report when wall-time is exceeded
