# ☀️ Hyper-Sprint Runbook (P7 Production-Ready)

## 🎯 觸發條件 (Trigger Criteria)
- **High Complexity**: 任務描述包含 "race", "deadlock", "timeout", "flaky"。
- **High Risk**: `research:route` 判斷 `risk=HIGH` 或 `confidence < 0.75`。
- **Feature Development**: 所有新功能開發建議優先進入 Hyper-Sprint。

## 🛠️ 參數模板 (Parameter Templates)

### 1. 標準 Bugfix (Baseline First)
```bash
uv run scripts/engine/nexus_cli.py nexus research:auto-flow \
  --task-desc "Fix flaky timeout in auth service" \
  --target-file "nexus/services/auth.py" \
  --test-file "tests/test_auth_flaky.py" \
  --candidate-count 1
```

### 2. 困難併發問題 (Gladiator Mode)
```bash
uv run scripts/engine/nexus_cli.py nexus research:sprint \
  --task "Fix deadlock between DB and Cache" \
  --target-file "nexus/db/sync.py" \
  --test-file "tests/test_deadlock.py" \
  --candidate-count 3 \
  --max-rounds 3
```

## 🚨 故障處理 (Troubleshooting)

| 症狀 (Symptom) | 可能原因 | 處置行動 (Action) |
| :--- | :--- | :--- |
| `broker_timeout` | Swarm 資源耗盡 | 檢查 `.nexus-swarm-*` 鎖定狀態，執行 `nexus:clean`。 |
| `quota_backoff` | LLM 達限 (429) | 切換為 `--no-llm-mode` 或增加 `--stage1-timeout-sec`。 |
| `no_change_candidate` | 提示詞無效 | 調整 `--task-desc`，增加更具體的 `mutation_hint`。 |

## ✅ DoD (Definition of Done)
- [ ] 100% 通過基準測試 (Green in Baseline or Hyper)。
- [ ] 產出 `.nexus/reports/research/sprint-report.json`。
- [ ] 回歸率 (Regression Rate) < 5%。
