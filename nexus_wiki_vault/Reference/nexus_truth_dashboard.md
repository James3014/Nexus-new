---
id: nexus_truth_dashboard
type: doc
status: active
created: 2026-04-07T07:29:29Z
updated: 2026-04-07T07:29:29Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/nexus_truth_dashboard.md
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
# 📊 Nexus Data Truth Dashboard (Audit-Grade Estimate)

> [!NOTE]
> 這是基於真實回放與回歸測試數據生成的動態儀表板。所有 Token 與漂移指標均由系統自動歸集，排除手動填寫。

## 📈 核心品質指標 (Latest Verified Run)

| 指標 | 數值 | 狀態 | 閾值 |
| :--- | :--- | :--- | :--- |
| **平均成功率 (Success Rate)** | 100% | ✅ PASS | > 95% |
| **平均健康度 (Avg Health)** | 99.8% | ✅ PASS | > 90% |
| **平均消耗 (Avg Tokens)** | 115.0 | ✅ VERIFIED | Audit-Grade Estimate |
| **最大漂移 (Max Drift)** | 0.00 | ✅ STABLE | < 0.5 |
| **採集狀態 (Capture Status)** | 0% 空值 | ✅ PASS | 不可空值 |
| **Raw Tokens 總量** | 0 | ⚠️ PARTIAL | 目前仍為 Estimate 模式 |

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
| OFF-010 | Full Lifecycle | Audit | ✅ OK | E2E [[Validation|Validation]] |

## 🛡️ 自動化攔截 ([[CD Promotion Gate|CI Gate]] Status)

- **Pytest Regression**: ✅ PASSING
- **Offline Replay**: ✅ PASSING
- **Drift Protection**: ✅ ACTIVE
- **Token Capture Integrity**: ✅ 0 empty
- **Raw Token Availability**: ⚠️ 0 (Audit-Estimate mode)

---
## 🛠️ 維護與更新指南 (Maintenance Guide)

> [!TIP]
> 此儀表板應由 CI/CD 或定時任務更新，禁止手動修改核心指標。

### 更新指令 (Update Command)
若要手動更新此儀表板數據，請執行：
```bash
uv run scripts/ci_gate.py && uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output nexus_truth_dashboard.csv
```

### 數據來源 ([[Source [[index|Index]]|[[Source [[index|Index]]|[[Source [[index|Index]]|[[Source [[index|Index]]|Sources]]]]]]]])
- **核心指標**: `ci_benchmark.csv` (由 `ci_gate.py` 產出)
- **回歸測試**: `tests/test_v9_regression_p1.py`
- **Token 正則驗證**: `tests/test_llm_token_regex.py`

*Last Updated: 2026-03-18 (post ci_gate re-verify)*


---
[[System Overview]]