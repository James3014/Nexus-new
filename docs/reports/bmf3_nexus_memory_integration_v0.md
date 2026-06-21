# BMF3 Nexus Memory Integration v0

Date: 2026-06-21

## Status

Final decision: `BMF3_NEXUS_MEMORY_INTEGRATION_READY`.

Local unit verified. This report is internal-only and does not grant public claim, production, or training export eligibility.

## Change Log

- `nexus/services/local_heal/memory_trace.py`: extended ctx-scoped trace with composite sources, memory evidence ids, and learning/findings linkage fields.
- `nexus/services/local_heal/memory_retrieval_adapter.py`: replaced default local JSONL-only retrieval with a fail-open composite store over LearningClosure JSONL, FindingsMemoryStore, and optional MemoryRepository.
- `nexus/services/local_heal/receipt.py`: removed adapter class-state fallback; receipt now reads only `ctx` or `ctx.op` memory trace.
- `nexus/services/local_heal/native_evidence_packet.py`: replaced hardcoded memory heuristics with `MemoryRetrievalAdapter.retrieve_reranked()`.
- `nexus/services/local_heal/learning_closure_bridge.py`: writes FindingsCard records through FindingsMemoryStore in addition to JSONL, fail-open.
- `nexus/research/findings_vector_sync.py`: maps FindingsCard `body` to MemoryRepository `content` before optional vector sync.
- `nexus/services/local_heal/semantic_anchor_selection.py`: caps prior-memory scoring and suppresses positive memory on traceback/transport candidates so memory cannot override behavior ownership.
- `nexus/services/local_heal/orchestrator.py`: attaches a bounded ctx-scoped memory trace before receipt writing and learning-closure writeback.
- `tests/unit/local_heal/test_bmf3_nexus_memory_integration.py`: added focused integration contract tests.

## Verification Evidence

- `uv run pytest tests/unit/local_heal/test_bmf3_nexus_memory_integration.py -q`: 12 passed, 1 warning.
- `uv run pytest tests/unit/local_heal/test_real_capability_wiring.py -q`: 12 passed, 1 warning.
- `uv run pytest tests/unit/local_heal/test_bg_evidence_compression_v2.py -q`: 16 passed.
- `uv run pytest tests/unit/local_heal/test_receipt_v1_schema.py -q`: 19 passed.
- `uv run pytest tests/unit/local_heal/test_semantic_anchor_selection.py -q`: 16 passed.
- `uv run pytest tests/unit/local_heal/test_h2_anchor_scorer.py::test_traceback_does_not_override_output_intent tests/unit/local_heal/test_h2_anchor_scorer.py::test_c12481_fixture_selects_new_over_read -q`: 2 passed.
- `uv run pytest tests/unit/local_heal -q`: 376 passed, 1 warning.
- `uv run python -m compileall -q ...`: passed for changed Python modules.

## Required Artifacts

- `artifacts/runtime/bmf3_nexus_memory_integration_v0/preflight_worktree_state.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/memory_trace_contract.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/call_path_audit.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/composite_memory_store_audit.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/validation_summary.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/anti_overfit_governance_audit.json`
- `artifacts/runtime/bmf3_nexus_memory_integration_v0/final_decision.json`

## Final Answers

1. Was `_last_memory_trace` removed? Yes. Implementation has no module/global/class fallback; remaining source hits are doc/test negative assertions.
2. Does receipt still import `semantic_anchor_selection` global state? No.
3. Explicit trace flow: `HealOrchestrator._finalize_run` -> `_attach_memory_influence_trace` -> `MemoryRetrievalAdapter.retrieve_reranked` -> `build_memory_trace_from_adapter` -> `ctx.op._memory_influence_trace` -> `receipt.telemetries.memory_influence` -> `LearningClosureBridge`.
4. Existing Nexus memory systems reused: LearningClosure JSONL, FindingsMemoryStore/FindingsCard, FindingsVectorSync, optional MemoryRepository/LanceDB.
5. Retrieval includes LearningClosure JSONL: yes.
6. Retrieval includes FindingsMemoryStore: yes.
7. LanceDB/MemoryRepository optional and fail-open: yes.
8. `native_evidence_packet` uses real memory instead of hardcoded heuristics: yes.
9. LearningClosure writeback syncs to FindingsMemoryStore: yes, fail-open.
10. Receipts include selected ids, provenance count, retrieval sources: yes via `MemoryTrace.to_dict()`.
11. Stale trace leakage across sequential receipts: covered by ctx/op-only tests.
12. Ranking remained unchanged? Mostly, but prior-memory scoring was deliberately capped after live FindingsMemory introduced a real H2 owner-regression; this change is recorded in the governance audit and verified by H2 tests.
13. Verifier behavior remained unchanged: yes, memory trace attach does not set solve eligibility or bypass verifier gates.
14. Did all tests pass? Yes for the required BMF9 commands and `tests/unit/local_heal`.
15. Safe to run trace-quality validation pack next? Yes, as an internal-only trace-quality pack, not public/product validation.

## Residual Debt

- GitNexus verification has limits. `npx gitnexus status` showed a stale index; `npx gitnexus analyze` was interrupted after over 120 seconds and ended with a Napi cleanup error. `HealOrchestrator` stale-index impact was LOW. `npx gitnexus detect_changes --repo actionlint` completed, but included unrelated shared-worktree dirt and reported medium risk across 34 files / 14 symbols.
- No live LanceDB probe was run. Optional MemoryRepository sync is unit-verified with a fake registry/repository.
- The shared worktree had substantial unrelated dirty state before this task; this report only covers the memory-integration files listed above.
