# Topology Truth Table

| Topology | Selected by Planner? | Read from signal_snapshot? | Env var fallback? | Real provider possible? | Candidate isolation? | Verifier invoked? | Mutation allowed default? | public_claim_allowed default? | production_ready default? | Tested by | Status |
|----------|---------------------|---------------------------|-------------------|------------------------|---------------------|-------------------|--------------------------|------------------------------|--------------------------|-----------|--------|
| single_local_model | Yes | Yes | No | Yes (Ollama) | No | No | No | False | False | test_local_model_executor.py | PASS |
| local_committee_only | Yes | Yes | No | Yes (Ollama) | Yes | Yes | No | False | False | test_local_model_executor.py | PASS |
| localheal_pipeline | Yes | Yes | No | Yes (Ollama) | Yes | Yes | No | False | False | test_localheal_pipeline_seam_truth.py | PARTIAL (rank_bm25 missing) |
| cloud_with_local_assist | Yes | Yes | No | No (shadow only) | No | No | No | False | False | test_local_model_executor.py | PASS (shadow) |

## Notes
- **Selected by Planner**: All topologies are selected via `signal_snapshot.execution_topology` from `CapabilityPlanner`
- **Read from signal_snapshot**: `_resolve_execution_topology()` reads strictly from `route_context.signal_snapshot`
- **Env var fallback**: Not allowed; missing signal_snapshot raises ValueError
- **Real provider possible**: Only Ollama provider is available; cloud providers are shadow-only stubs
- **Candidate isolation**: local_committee_only and localheal_pipeline use `run_isolated_workspace_apply` + `run_isolated_verifier`
- **Verifier invoked**: local_committee_only and localheal_pipeline invoke verifier if `verifier_allowed=True`
- **Mutation allowed**: Default False; requires `mutation_allowed=True` in signal_snapshot
- **public_claim_allowed**: Hard False in all receipt/verifier dataclasses
- **production_ready**: Hard False in all receipt/verifier dataclasses
