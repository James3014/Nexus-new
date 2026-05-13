[任務] -> P44 新路由能力接線結案審計

目標：確認新路由把該用的核心能力正確接上、正確調用、正確留證，並釐清哪些項目屬於 public capability funnel，哪些只是 internal marker。

[數據]

## 1. 接線本體審計
- `build_capability_wiring_audit()`：PASS
- high priority `registry_only`：0
- high priority `missing_receipt_policy`：0
- `pending_executor_without_spec`：0

結論：核心能力不是「沒接上」，而是後續要區分實際執行能力與 route/internal marker。

## 2. 靜態/本地驗證
- `uv run pytest -q tests/engine/test_capability_wiring_audit.py tests/ops/test_capability_invocation_matrix.py tests/engine/test_harness_sensors.py tests/engine/test_mutation_assurance.py`
- 結果：`18 passed`

## 3. Route smoke 與 capability union
- 既有 summary：`.nexus/reports/capability_route_smoke_summary.json`
- verdict：`PASS`
- suites：
  - `route_oracles`
  - `codeintel_hyper`
  - `core_governance_gates`
  - `belief_gate`
  - `runtime_receipt_oracles`
  - `harness_engineering_oracles`

### route runtime required union
- `autoreason`
- `belief`
- `ddtree`
- `drone`
- `lancedb`
- `nightshift`
- `research`
- `semantic_searcher`
- `swarm`
- `swarm_quiet_moment`
- `ultra_review`

expected union 與 public-safe union 完整一致。

## 4. Flash+Nexus 真實證據
- same-model guarded A/B：
  - report：`.nexus/reports/p35_flash_ab_guarded/gemini_nexus_report_1778569995.md`
  - `with_nexus`: `2/2 eligible`, `solve_rate=1.0`, `semantic_verified=1.0`, `trust_mismatch=0.0`
  - `without_nexus`: `2/2 eligible`, `solve_rate=0.0`
- protected Nexus-only guarded rerun：
  - report：`.nexus/reports/p35_flash_nexus_default_guarded/gemini_nexus_report_1778569537.md`
  - `route-oracle-autoreason-001`: PASS
  - `route-oracle-ddtree-001`: PASS

## 5. 核心能力覆蓋結果

### 已完成 `selected -> invoked -> evidence -> public_safe -> outcome`
- `codeintel`
- `research`
- `hyper`
- `nightshift`
- `swarm`
- `drone`
- `ultra_review`
- `autoreason`
- `ddtree`
- `lancedb`
- `memory`
- `mempalace_gate`
- `belief`
- `artifact_gate`
- `claim_gate`
- `delivery_gate`
- `semantic_searcher`
- `semantic_failure_sensor`
- `swarm_quiet_moment`
- `harness_preflight_sensor`
- `bdd_acceptance_skill`

### 仍未進 public evidence funnel，但原因已釐清
- `pregate`
- `plan_quality_gate`
- `sandbox`
- `acceptance_check`

這四項不是「完全沒用到」，而是目前設計上屬於 internal marker / governance marker 類。舊報告 `docs/reports/GEMINI_FLASH_NEXUS_P16_P17_2026-05-05.md` 已明確記錄：
- `research_route`, `pregate`, `sandbox`, `learn_*`, `plan_quality_gate`, `acceptance_check` 應拆成 internal markers，不應污染 public route-quality funnel。

因此本輪不把它們列為 executor wiring failure，也不為了湊 coverage 把它們強行塞進 public capability claim。

## 6. P44 結論
- P37 接線審計：完成
- P38 route smoke：完成
- P40 Flash route-oracle/guarded evidence：完成
- P41 Flash same-model A/B：完成
- P42 核心能力零使用檢查：完成，無 unexplained executor gap

P44 可結案的精確表述：
- 新路由的核心 executable/public-safe 能力已正確接線並有 benchmark 證據。
- 沒有發現「核心 executor 完全沒接上」或「應該 public-safe 卻完全沒 invoked/evidence」的未解釋缺口。
- 尚未進 public evidence funnel 的 `pregate / plan_quality_gate / sandbox / acceptance_check`，目前應按 internal marker 解讀，不應當成 route wiring regression。

[證據]
- wiring audit：`nexus/engine/capability_wiring_audit.py`
- invocation matrix：`scripts/ops/capability_invocation_matrix.py`
- route smoke：`.nexus/reports/capability_route_smoke_summary.json`
- Flash guarded A/B：`.nexus/reports/p35_flash_ab_guarded/gemini_nexus_report_1778569995.md`
- Nexus guarded rerun：`.nexus/reports/p35_flash_nexus_default_guarded/gemini_nexus_report_1778569537.md`
- route-quality/internal-marker precedent：`docs/reports/GEMINI_FLASH_NEXUS_P16_P17_2026-05-05.md`
