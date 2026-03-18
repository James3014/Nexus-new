# Nexus Phase Health Autonomy Design (v0)

> [!important]
> **Status**: `ACTIVE` / `ERA-C`

## 1. 目的與範圍
本設計定義 Nexus 在 `P -> X -> D -> R -> A -> C` 六階段中的自動健康監測、主動修復（Self-Heal）與主動優化（Self-Optimize）機制。

目標：
1. 每階段可追蹤健康度（phase_health）。
2. 健康度低時自動插入修復任務，不需人工逐步指揮。
3. 學習力停滯時自動啟動優化任務，提升下一輪表現。
4. 保持與現有 `nexus:runner` + `task_manifest.yaml` 架構相容。

## 2. 現況與約束（2026-03-18）
1. `ci_gate` 與 benchmark replay 已可達 `PASS`，`Average Health` 高於門檻。
2. `raw token` 仍可能為 `0`（Audit-Estimate 模式），不可作為唯一阻斷條件。
3. 任務治理以 `nexus:runner` 為單一入口，僅在 destructive/credential/spec_conflict 停下詢問。

## 3. 核心概念

### 3.1 phase_health
`phase_health` 為單一 phase 的健康分數，範圍 `0~100`。

### 3.2 pipeline_health
`pipeline_health` 為當輪整體健康度，從各 phase_health 加權計算。

### 3.3 learning_velocity
`learning_velocity` 衡量最近 N 輪是否有效成長（成功率、重試數、token效率、回歸穩定性）。

## 4. Phase 指標定義

### P (Plan)
- 指標：plan_completeness、dependency_validity、spec_clarity
- health 計算：
  - `P.health = 0.4*plan_completeness + 0.4*dependency_validity + 0.2*spec_clarity`

### X (Explore/Research)
- 指標：evidence_quality、source_relevance、research_latency
- health 計算：
  - `X.health = 0.45*evidence_quality + 0.35*source_relevance + 0.20*(100-research_latency_norm)`

### D (Diagnose)
- 指標：root_cause_confidence、diagnosis_precision、false_positive_rate
- health 計算：
  - `D.health = 0.4*root_cause_confidence + 0.4*diagnosis_precision + 0.2*(100-false_positive_rate)`

### R (Repair)
- 指標：fix_success_rate、retry_penalty、scope_drift
- health 計算：
  - `R.health = 0.5*fix_success_rate + 0.3*(100-retry_penalty) + 0.2*(100-scope_drift)`

### A (Audit)
- 指標：regression_pass_rate、side_effect_score、coverage_signal
- health 計算：
  - `A.health = 0.5*regression_pass_rate + 0.3*side_effect_score + 0.2*coverage_signal`

### C (Crystal)
- 指標：pattern_reuse_rate、lesson_quality、next_run_hit_rate
- health 計算：
  - `C.health = 0.4*pattern_reuse_rate + 0.3*lesson_quality + 0.3*next_run_hit_rate`

## 5. 自主修復策略（Health Auto-Repair）

### 5.1 觸發條件
任一條件成立即觸發：
1. 任一 phase_health `< 85` 連續 2 輪。
2. `pipeline_health < 88`。
3. `A.health < 90` 且 regression 任務有 FAIL。

### 5.2 自動動作
1. 在 `task_manifest.yaml` 動態注入 `auto.repair.<phase>` 任務。
2. 插入位置：
   - `P/X/D` 問題：插入 `D -> R -> A` 子鏈。
   - `R` 問題：插入 `R -> A` 子鏈。
   - `A` 問題：插入 `A.recheck` + `side_effect_scan`。
3. 重試上限：`max_retry=2`。
4. 超過上限改 `on_fail: escalate`。

### 5.3 範例任務
```yaml
- id: auto.repair.r.low_health
  depends_on: [bench.replay]
  run: "uv run scripts/engine/nexus_cli.py nexus:runner --task auto.repair.r.low_health"
  done_when:
    type: command_rc_zero
  on_fail: escalate
  max_retry: 2
  ask_policy: no_ask
```

## 6. 自主優化策略（Learning Auto-Optimize）

### 6.1 觸發條件
任一條件成立即觸發：
1. learning_velocity 連續 3 輪 `<= 0`。
2. success_rate 無提升且 retry_count 連續上升 2 輪。
3. `C.health < 80`。

### 6.2 自動動作
1. 注入 `auto.optimize.learning` 任務包。
2. 任務包內容：
   - 更新 router 選擇權重（降低失效技能權重）。
   - 更新 context 剪枝規則（減少低價值歷史內容）。
   - 生成 `crystal_delta.md` 記錄本輪學習與下輪假設。
3. 驗收：下一輪至少一項改善：
   - success_rate 增加
   - avg_health 增加
   - retry_count 降低
   - token_efficiency 改善

## 7. 資料結構（建議 schema）

### 7.1 state 擴充欄位
```json
{
  "phase_metrics": {
    "P": {"health": 0, "signals": {}},
    "X": {"health": 0, "signals": {}},
    "D": {"health": 0, "signals": {}},
    "R": {"health": 0, "signals": {}},
    "A": {"health": 0, "signals": {}},
    "C": {"health": 0, "signals": {}}
  },
  "pipeline_health": 0,
  "learning_velocity": 0,
  "auto_actions": [
    {"type": "repair", "phase": "R", "reason": "R.health<85 x2", "ts": "..."}
  ]
}
```

### 7.2 證據路徑
1. `.nexus/task_status.json`
2. `.nexus/runs/<run_id>/phase_metrics.json`
3. `docs/EXEC_LIVE_STATUS.md`
4. `ci_benchmark.csv`

## 8. 任務排序調整（依現況）
現況已是 `Gate PASS`，建議優先序調整如下：
1. **P0**：導入 `phase_health` 記錄（先有觀測）。
2. **P0**：導入 `auto.repair.on_low_health`（先有自癒）。
3. **P1**：導入 `learning_velocity` 計算與 `auto.optimize.on_low_learning`。
4. **P1**：將自動動作寫回 INDEX/EXEC 狀態面板。
5. **P2**：再推進 orbit scheduler 與 15 能力擴充。

## 9. 落地步驟（最小可行）
1. 在 runner 輸出中新增 phase_metrics 落檔。
2. 在 task_manifest 增加兩個系統任務：
   - `auto.repair.on_low_health`
   - `auto.optimize.on_low_learning`
3. 在 ci_gate 摘要中增加：
   - lowest_phase_health
   - learning_velocity
4. 更新 INDEX 的 Current/Next，將健康自治列為近期主線。

## 10. 驗收標準（DoD）
1. 六個 phase 都能產生 health 分數。
2. 低健康觸發後可自動插入 repair 任務並完成。
3. 低學習力可觸發 optimize 任務，且下一輪至少一項指標改善。
4. 全流程無需人工逐步確認（符合 no_ask 原則），僅在高風險事件停下。
