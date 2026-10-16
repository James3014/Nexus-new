# Code Slices

## 1. nexus/services/local_heal/local_model_executor.py

### LocalModelExecutorRequest dataclass (L32-L47)
```python
@dataclass(frozen=True)
class LocalModelExecutorRequest:
    task_id: str
    problem_statement: str
    repo_root: str
    target_file: str
    selected_capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    receipt_context: dict[str, Any] = field(default_factory=dict)
    route_context: dict[str, Any] = field(default_factory=dict)
    model_name: str = ""
    dry_run: bool = True
    mutation_allowed: bool = False
    verifier_allowed: bool = False
    execution_topology: str = "single_local_model"
```

### _resolve_execution_topology (L64-L87)
```python
def _resolve_execution_topology(request: LocalModelExecutorRequest) -> str:
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    signal_snapshot = route_ctx.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        raise ValueError("Missing signal_snapshot in route_context")
    topology = signal_snapshot.get("execution_topology")
    if not topology:
        raise ValueError("Missing execution_topology in signal_snapshot")
    if "protocol_mode" not in signal_snapshot:
        raise ValueError("Missing protocol_mode in signal_snapshot")
    if topology != "local_committee_only":
        if "executor_model" not in signal_snapshot:
            raise ValueError("Missing executor_model in signal_snapshot")
    return str(topology)
```

### build_local_model_provider_from_signal_snapshot (L413-L448)
```python
def build_local_model_provider_from_signal_snapshot(
    route_context: Mapping[str, Any],
    injected_fn_key: str,
) -> LocalModelProvider:
    signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
    if not isinstance(signal_snapshot, dict):
        return InertLocalModelProvider()
    if "model_call_allowed" not in signal_snapshot:
        raise ValueError("Missing model_call_allowed in signal_snapshot")
    call_allowed = bool(signal_snapshot["model_call_allowed"])
    if not call_allowed:
        return InertLocalModelProvider()
    injected_fn = route_context.get(injected_fn_key)
    if injected_fn is not None:
        return InjectedLocalModelProvider(injected_fn)
    provider_type = signal_snapshot.get("executor_provider")
    model_name = signal_snapshot.get("executor_model")
    if not provider_type or not model_name:
        raise ValueError("Missing executor_provider or executor_model in signal_snapshot")
    provider_type = provider_type.lower()
    model_name = model_name.strip()
    if provider_type == "ollama" and model_name:
        return OllamaLocalModelProvider()
    return InertLocalModelProvider()
```

### local_committee_only branch (L928-L1427)
```python
if execution_topology == "local_committee_only":
    signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
    protocol_mode = signal_snapshot["protocol_mode"]
    # ... enhanced_problem construction ...
    candidates = LocalCommitteeCandidateProvider.generate_committee_candidates(...)
    decision = CandidateDecisionAdapter.select_candidate(candidates, ...)
    local_model_called = any(not c.abstained for c in candidates)
    selected_patch = decision.selected_candidate_patch
    # ... candidate isolation + verifier + hybrid_route ...
```

### localheal_pipeline branch (L1429-L2447)
```python
if execution_topology == "localheal_pipeline":
    repair_exec = LocalHealPipelineCapabilityExecutor().execute(cap_ctx)
    ddtree_exec = DDTreeLocalExecutor().execute(cap_ctx)
    autoreason_exec = AutoreasonLocalExecutor().execute(cap_ctx)
    artifact_exec = ArtifactGateLocalExecutor().execute(cap_ctx)
    claim_exec = ClaimGateLocalExecutor().execute(cap_ctx)
    delivery_exec = DeliveryGateLocalExecutor().execute(cap_ctx)
    pipeline_final_patch = repair_exec.telemetries.get("pipeline_final_patch", "")
    # ... projection + isolation + verifier ...
```

### cloud_with_local_assist branch (L2449-L2715)
```python
if execution_topology == "cloud_with_local_assist":
    stage1 = _p3_stage1_local_diagnosis(request)
    cloud_provider = FakeCloudCandidateProvider()
    cloud_response = cloud_provider.generate(request)
    stage3 = _p3_stage3_cheap_verifier(cloud_response.candidate_patch, request)
    # ... shadow routing, falls through to single_local_model ...
```

## 2. nexus/services/local_heal/local_model_capability_executors.py

### LocalHealPipelineCapabilityExecutor.execute (L199-L801)
```python
class LocalHealPipelineCapabilityExecutor:
    name = "repair_loop"
    phase = "R"
    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Checks module availability, runs pipeline if topology matches
        # Returns CapabilityExecutionResult with telemetry fields:
        # - localheal_pipeline_available
        # - localheal_pipeline_run_called
        # - localheal_pipeline_actual_execution
        # - localheal_pipeline_availability_only
```

## 3. nexus/services/local_heal/local_committee_candidate_provider.py

### generate_committee_candidates
```python
class LocalCommitteeCandidateProvider:
    @staticmethod
    def generate_committee_candidates(
        task_id: str,
        problem_statement: str,
        target_file: str,
        target_symbol: str,
        locked_search: str,
        evidence_refs: tuple[str, ...],
        provider: LocalModelProvider,
        protocol_mode: str,
        route_context: dict[str, Any],
    ) -> list[CandidateEnvelope]:
        # Generates committee candidates from proposer_specs
```

## 4. nexus/services/local_heal/candidate_decision_adapter.py

### select_candidate
```python
class CandidateDecisionAdapter:
    @staticmethod
    def select_candidate(
        candidates: list[CandidateEnvelope],
        selected_capabilities: tuple[str, ...],
        ctx: LocalModelCapabilityContext,
    ) -> CandidateDecisionResponse:
        # Selects best candidate by truth priority
        # Returns CandidateDecisionResponse with selected_candidate_id/patch
```

## 5. nexus/services/local_heal/isolated_local_solve_loop.py

### run_isolated_local_solve_loop (L80-L308)
```python
def run_isolated_local_solve_loop(request: IsolatedLocalSolveRequest) -> IsolatedLocalSolveResponse:
    envelope = parse_local_model_patch_envelope(request.task_id, request.model_output)
    # ... normalization + anchor + apply + verifier + isolation ...
    isolation_receipt = CandidateIsolationReceipt(...)
    hr_decision = candidate_isolation_to_hybrid_route(isolation_receipt)
    return IsolatedLocalSolveResponse(...)
```

### IsolatedApplyReceipt (isolated_workspace_apply.py L24-L38)
```python
@dataclass(frozen=True)
class IsolatedApplyReceipt:
    task_id: str
    workspace_path: str
    target_file: str
    patch_apply_status: str
    patch_apply_error: str
    selected_candidate_hash: str
    applied_patch_hash: str
    selected_candidate_hash_matches_applied: bool
    candidate_output_isolated: bool
    mutation_allowed: bool
    public_claim_allowed: bool = False
    production_ready: bool = False
    applied_patch_hash_source: str = ""
```

### IsolatedVerifierReceipt (isolated_verifier.py L17-L28)
```python
@dataclass(frozen=True)
class IsolatedVerifierReceipt:
    task_id: str
    verifier_status: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    verifier_error: str
    verifier_allowed: bool
    public_claim_allowed: bool = False
    production_ready: bool = False
```

### CandidateIsolationReceipt (candidate_isolation_gate.py L16-L33)
```python
@dataclass(frozen=True)
class CandidateIsolationReceipt:
    candidate_id: str
    selected_candidate_hash: str
    applied_patch_hash: str
    selected_candidate_hash_matches_applied: bool
    candidate_output_isolated: bool
    verifier_result: VerifierResult | str
    evidence_refs: tuple[str, ...]
    local_model_called: bool = False
    mutation_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    repaired_by_rule: str = "none"
    candidate_target_file: str = ""
    candidate_target_symbol: str = ""
    candidate_old_block_hash: str = ""
```
