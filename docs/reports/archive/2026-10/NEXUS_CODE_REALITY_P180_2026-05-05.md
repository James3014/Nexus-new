# Nexus Code-Reality P180 Closeout

## Task
P149-P180 converted the Brain Hub / strategic-map refactor plan from document alignment into executable gates.

## Completed
- P149-P153: Brain Hub manifest and benchmark policy gate landed in `e59dc499`.
- P154-P160: HallucinationGuard drift CLI, ContextHub strict dependency mode, and StateContract regression tests landed in `58a112f4`.
- P161-P168: Strategic map manifest and audit gate landed in `d2199a78`.
- P169-P175: Evolution protocol runtime seam added for L3/L4 forgetting, Quiet Moment, and shadow promotion boundaries.

## Gate Results
- `uv run pytest -q tests/ops/test_hallucination_guard_drift.py tests/core/test_context_hub_strict_deps.py tests/core/test_state_contracts.py tests/core/test_hallucination_guard.py`: 21 passed.
- `uv run pytest -q tests/ops/test_strategic_map_audit.py tests/ops/test_hallucination_guard_drift.py tests/core/test_context_hub_strict_deps.py tests/core/test_state_contracts.py tests/infrastructure/test_storage_implementations.py`: 14 passed.
- `uv run pytest -q tests/core/test_evolution_protocols.py tests/core/test_healing_artifacts.py tests/security/test_secure_sync.py tests/ops/test_strategic_map_audit.py tests/ops/test_brain_hub_audit.py tests/ops/test_hallucination_guard_drift.py`: 25 passed.
- `uv run pytest -q tests/ops/test_capability_route_smoke.py tests/ops/test_research_stack_route_smoke.py`: 16 passed.
- `python3 scripts/ops/brain_hub_audit.py --manifest docs/ops/brain_hub_manifest.json`: passed, failures=[]
- `python3 scripts/ops/hallucination_guard_drift.py`: passed, failures=[]
- `python3 scripts/ops/strategic_map_audit.py`: passed, failures=[]
- `python3 scripts/ops/capability_route_smoke.py --print-only`: passed=true, failures=[]
- `python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_gemini3flash_value4x1_20260505_p147/with_nexus_1777986380.jsonl --require-autoreason-invoked`: passed=true.

## Measured Route Evidence
From the P147 Flash 4x1 with-Nexus JSONL:
- Rows: 4
- Source projects seen: autoreason, autoresearch, autoresearchclaw, codex-autoresearch
- Checkpoints seen: candidate_tournament_receipt, claim_citation_verification, fixed_budget_metric_contract, packet_session_ledger
- Research public safe: 4/4
- Research doctor pass: 4/4
- Claim probe gate: 4/4
- Autoreason selected/invoked: 4 selected, 2 invoked
- Autoreason AB factory ready: 2
- Autoreason AB winner: 2
- Route Quality: selected->invoked 95%, invoked->evidence 100%, evidence->outcome 100%, unnecessary selected 5%

## Benchmark Decision
No new Flash 12x2 or Pro run was launched in P149-P180. The changes were gate/contract/runtime-seam changes, not a new public performance claim. Per `docs/ops/NEXUS_BENCHMARK_POLICY_2026-05-05.md`, route/report/gate changes require targeted pytest plus route/research smoke first; long benchmark only runs for public-claim promotion.

## Residual Debt
- `capability_route_smoke --print-only` verifies route identity and command construction only; a full execution smoke can be run when touching executors or benchmark rows again.
- ContextHub still keeps fallback mode for backwards compatibility; strict dependency mode is now available and tested, but not forced globally.
- Evolution protocols are currently non-mutating guard seams; deeper integration into swarm broker / secure sync event handling remains P181+.

## Next Plan P181-P195
- P181-P184: wire `evolution_protocols.build_quiet_moment_event` into swarm/healing report emission without allowing production writes.
- P185-P188: make `strategic_map_audit.py` part of CI gate selection for files in `nexus/core`, `nexus/infrastructure`, `nexus/security`, and Brain Hub wiki.
- P189-P191: add full route execution smoke only for executor-affecting changes, with infra-invalid classification before result interpretation.
- P192-P195: update public report engine to include Brain Hub Manifest, Strategic Map, and Evolution Boundary sections when evidence is present.
