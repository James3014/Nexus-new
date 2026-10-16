# N24 Closeout: 7 個 S/P/X fallback 真實化

**Status**: PASS

## 7 個能力 fallback → 真實
- policy_capability_gate: 補 route_id/original_score/health_metrics/repo_root → invoked=True
- nightshift_runner_service: 已可 (補 task 參數) → invoked=True
- decision_formula_engine: 補 context dict → invoked=True
- codeintel: 已可 (root="/tmp") → invoked=True
- lancedb: 已可 (JSON fallback mode active) → invoked=True
- research: 已可 (project_root="/tmp") → invoked=True
- research_and_source_discipline: 補 root="/tmp" → invoked=True

## 測試
- 7 個新 test PASS
- 既有 583 test 不退步

## Forbidden claims
- 不可聲稱 production_ready
- 不可聲稱 36 個能力全真實跑 (只 17 個, 19 個仍 fallback)
- 可聲稱 N24 7 個能力 fallback → 真實
