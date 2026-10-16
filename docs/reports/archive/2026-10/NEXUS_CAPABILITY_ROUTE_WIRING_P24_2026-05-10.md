# Nexus Capability Route Wiring P24

## Goal

確保新路由在「應該使用某能力」時能完成四層接線：

- registry node 存在
- receipt adapter 存在
- receipt policy 可審核
- smoke/runtime 產生 public-safe receipt

## P1-P24 Closure

| Phase | Result | Evidence |
|---|---:|---|
| P1-P3 wiring audit | PASS | `build_capability_wiring_audit()` passed |
| P4-P6 missing high-priority adapters | PASS | high-priority missing adapter = 0 |
| P7-P9 receipt policy backing | PASS | high-priority missing receipt policy = 0 |
| P10-P13 MSA/JIT route hooks | PASS | `msa_router`, `jit_validation` registered and receipt-backed |
| P14-P17 unused reason taxonomy | PASS | `unused_reason_for_row()` covers not-selected, pending, no-payload, no-evidence, no-gate, no-outcome |
| P18-P21 full route smoke | PASS | `capability_route_smoke.py` passed |
| P22-P24 report/writeback | PASS | this report records failure lesson and verification evidence |

## Wiring Audit Snapshot

```json
{
  "capability_count": 51,
  "passed": true,
  "status": {
    "runtime_backed": 44,
    "receipt_backed_pending_executor": 3,
    "receipt_backed_shadow": 3,
    "deprecated_alias": 1
  },
  "high_priority_registry_only": [],
  "high_priority_missing_adapter": [],
  "high_priority_missing_receipt_policy": [],
  "high_priority_pending_executor": ["drone", "nightshift", "swarm"]
}
```

## Smoke Evidence

`uv run python scripts/ops/capability_route_smoke.py`

```json
{
  "receipt_diagnostic_pass": true,
  "passed": true,
  "route_oracles": {
    "expected_capabilities": ["autoreason", "ddtree", "drone", "lancedb", "nightshift", "research", "swarm", "ultra_review"],
    "public_safe_capabilities": ["autoreason", "ddtree", "drone", "lancedb", "nightshift", "research", "swarm", "ultra_review"],
    "selected_to_invoked_rate": 0.9848484848484849,
    "invoked_to_evidence_rate": 1.0,
    "evidence_to_outcome_rate": 1.0,
    "unnecessary_selected_rate": 0.015151515151515152
  },
  "runtime_receipt_oracles": {
    "expected_capabilities": ["semantic_searcher", "swarm_quiet_moment"],
    "public_safe_capabilities": ["semantic_searcher", "swarm_quiet_moment"]
  }
}
```

## Failure Lesson

Full smoke initially failed on `route-oracle-autoreason-001`: planner selected `autoreason`, but promoted route-cost controls forced `candidate_cap=1` and `skip_llm_baseline=true`, so runtime skipped the candidate factory and produced no `autoreason` receipt.

Fix: route-cost slimming remains active for ordinary tasks, but explicit `expected_capabilities` now protect audited executor/evidence paths from being cost-pruned.

## Residual Debt

- `drone`, `swarm`, `nightshift` remain marked `receipt_backed_pending_executor`; they are public-safe in route-oracle smoke through receipt-backed shadow/pending semantics, not full production executors.
- This is a route/receipt diagnostic, not a public benchmark improvement claim.
