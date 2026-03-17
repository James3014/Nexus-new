# 📊 Nexus Data Truth Dashboard

> [!NOTE]
> 這是基於真實回放與回歸測試數據生成的動態儀表板。所有 Token 與漂移指標均由系統自動歸集，排除手動填寫。

## 📈 核心品質指標 (Latest Release)

| 指標 | 數值 | 狀態 | 閾值 |
| :--- | :--- | :--- | :--- |
| **平均成功率 (Success Rate)** | 100% | ✅ PASS | > 95% |
| **平均健康度 (Avg Health)** | 100.0% | ✅ PASS | > 90% |
| **平均消耗 (Avg Tokens)** | 0 | ⚠️ PENDING | 非零對標 |
| **最大漂移 (Max Drift)** | 0.00 | ✅ STABLE | < 0.5 |
| **單次任務平均耗時** | 4.1s | ⚡ FAST | < 10s |

## 🧪 測試矩陣覆蓋率 (Case Catalog)

| ID | 名稱 | 類型 | 狀態 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| OFF-001 | Basic Import Fix | Bug | ✅ OK | Smoke Test |
| OFF-002 | Add Endpoint | Feat | ✅ OK | Structural Add |
| OFF-003 | DI Conflict | Bug | ✅ OK | Stability Fix |
| OFF-004 | Fast Mode | Feat | ✅ OK | Path Skipping |
| OFF-005 | Strict Audit | Bug | ✅ OK | Safety Gate |
| OFF-006 | KB Guard | Bug | ✅ OK | Persistent Asset |
| OFF-007 | Dr. Claw | Bug | ✅ OK | Auto-Diagnostics |
| OFF-008 | Wheel-Shift | Feat | ✅ OK | LLM Allocation |
| OFF-009 | State Guard | Bug | ✅ OK | Contract Integrity |
| OFF-010 | Full Lifecycle | Audit | ✅ OK | E2E Validation |

## 🛡️ 自動化攔截 (CI Gate Status)

- **Pytest Regression**: ✅ PASSING
- **Offline Replay**: ✅ PASSING
- **Drift Protection**: ✅ ACTIVE

---
## 🛠️ 維護與更新指南 (Maintenance Guide)

> [!TIP]
> 此儀表板應由 CI/CD 或定時任務更新，禁止手動修改核心指標。

### 更新指令 (Update Command)
若要手動更新此儀表板數據，請執行：
```bash
uv run scripts/ci_gate.py && uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output nexus_truth_dashboard.csv
```

### 數據來源 (Sources)
- **核心指標**: `ci_benchmark.csv` (由 `ci_gate.py` 產出)
- **回歸測試**: `tests/test_v9_regression_p1.py`
- **Token 正則驗證**: `tests/test_llm_token_regex.py`

*Last Updated: 2026-03-17 20:25*
