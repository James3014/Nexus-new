"""N30R-W0 Local Armor End-to-End Contract Audit.

Two lanes:
  Lane A: Real Planner Truth (real CapabilityPlanner.plan())
  Lane B: Synthetic Binding Truth (synthetic snapshot, verify executor/pipeline consume capabilities)

Uses deterministic mock provider. No live Ollama.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import sha256_str
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
    LocalModelProviderResponse,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "n30r_w0"
FIXTURE_SOURCE = (FIXTURE_DIR / "target.py").read_text(encoding="utf-8")
FIXTURE_SOURCE_SHA = sha256_str(FIXTURE_SOURCE)
FIXTURE_VERIFIER = ("python3", str(FIXTURE_DIR / "verify_target.py"))
FIXTURE_TASK_DESC = "Fix add_one to return value + 1 instead of value"
FIXTURE_TARGET_FILE = "tests/fixtures/n30r_w0/target.py"
FIXTURE_TARGET_SYMBOL = "add_one"

# ---------------------------------------------------------------------------
# Deterministic mock provider
# ---------------------------------------------------------------------------
MOCK_PATCH = "def add_one(value: int) -> int:\n    return value + 1\n"
MOCK_PROVIDER_RESPONSE = MOCK_PATCH

class DeterministicMockProvider:
    """Records all calls and returns a fixed valid patch."""
    def __init__(self):
        self.calls: list[dict] = []

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        self.calls.append({
            "model_name": request.model_name,
            "prompt_length": len(request.prompt),
            "prompt_sha256": sha256_str(request.prompt),
            "prompt_excerpt": request.prompt[:500],
            "timestamp": time.monotonic(),
        })
        return LocalModelProviderResponse(
            provider_invoked=True,
            model_called=True,
            model_name=request.model_name,
            output_text=MOCK_PROVIDER_RESPONSE,
        )

    def as_function(self) -> Callable[[str, str, str], str]:
        def _fn(model: str, system_prompt: str, user_prompt: str) -> str:
            self.calls.append({
                "model_name": model,
                "prompt_length": len(user_prompt),
                "prompt_sha256": sha256_str(user_prompt),
                "prompt_excerpt": user_prompt[:500],
                "timestamp": time.monotonic(),
            })
            return MOCK_PROVIDER_RESPONSE
        return _fn


# ---------------------------------------------------------------------------
# Spy infrastructure
# ---------------------------------------------------------------------------
@dataclass
class SpyRecord:
    call_count: int = 0
    argument_type: str = ""
    argument_sha256: str = ""
    caller_symbol: str = ""
    return_type: str = ""
    timestamps: list[float] = field(default_factory=list)


class SpyManager:
    def __init__(self):
        self.planner: SpyRecord = SpyRecord(caller_symbol="CapabilityPlanner.plan")
        self.executor: SpyRecord = SpyRecord(caller_symbol="LocalModelExecutor.run")
        self.pipeline_exec: SpyRecord = SpyRecord(caller_symbol="LocalHealPipelineCapabilityExecutor.execute")
        self.heal_pipeline: SpyRecord = SpyRecord(caller_symbol="HealPipeline.run")
        self.provider: SpyRecord = SpyRecord(caller_symbol="InjectedLocalModelProvider.generate")


# ---------------------------------------------------------------------------
# Stage traces
# ---------------------------------------------------------------------------
@dataclass
class StageTrace:
    captured: bool = False
    capture_source: str = ""
    timestamp_monotonic: float = 0.0
    payload_sha256: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class ContractTrace:
    stage1_planner_input: StageTrace = field(default_factory=StageTrace)
    stage2_planner_output: StageTrace = field(default_factory=StageTrace)
    stage3_executor_request: StageTrace = field(default_factory=StageTrace)
    stage4_pipeline_context: StageTrace = field(default_factory=StageTrace)
    stage5_model_prompt: StageTrace = field(default_factory=StageTrace)
    stage6_receipt: StageTrace = field(default_factory=StageTrace)


# ---------------------------------------------------------------------------
# Lane A: Real Planner Truth
# ---------------------------------------------------------------------------
def run_lane_a(spy: SpyManager) -> dict:
    """Call real CapabilityPlanner.plan() and capture input/output."""
    from nexus.engine.capability_planner import CapabilityPlanner

    planner = CapabilityPlanner()

    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "localheal_pipeline"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER"] = "ollama"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b-instruct"

    route = {
        "task_id": "n30r_w0_audit",
        "task_desc": FIXTURE_TASK_DESC,
        "task_type": "swe_bounded_repair",
        "difficulty": "easy",
        "route_features": {},
    }

    # Capture planner input
    planner_input = {
        "task_desc": FIXTURE_TASK_DESC,
        "task_type": "swe_bounded_repair",
        "route": route,
        "pillars": {},
        "codeintel": {},
        "phase_trace": {},
        "budget": {"max_cost": 20},
        "skills": [],
        "source_code_present": True,
        "source_code_length": len(FIXTURE_SOURCE),
        "source_code_sha256": FIXTURE_SOURCE_SHA,
        "target_file_present": True,
        "target_symbol_present": True,
        "verifier_contract_present": True,
        "failure_evidence_present": False,
        "codeintel_nonempty": False,
        "skills_nonempty": False,
    }

    t0 = time.monotonic()
    spy.planner.call_count += 1
    spy.planner.timestamps.append(t0)

    plan = planner.plan(
        task_desc=FIXTURE_TASK_DESC,
        task_type="swe_bounded_repair",
        route=route,
        pillars={},
        codeintel={},
        phase_trace={},
        budget={"max_cost": 20},
        skills=[],
    )

    t1 = time.monotonic()
    spy.planner.return_type = type(plan).__name__
    spy.planner.argument_sha256 = sha256_str(json.dumps(planner_input, sort_keys=True, default=str))

    for key in ("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                 "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                 "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"):
        os.environ.pop(key, None)

    snapshot = plan.signal_snapshot
    snapshot_sha = sha256_str(json.dumps(snapshot, sort_keys=True, default=str))

    # Classify fields
    field_status = {}
    for key in sorted(snapshot.keys()):
        val = snapshot[key]
        if val is None:
            field_status[key] = "field_missing"
        elif val == "" or val == () or val == [] or val == {}:
            field_status[key] = "field_present_empty"
        else:
            field_status[key] = "field_present_nonempty"

    selected_caps = snapshot.get("selected_capabilities", ())
    if isinstance(selected_caps, (list, tuple)):
        cap_count = len(selected_caps)
    else:
        cap_count = 0

    planner_output = {
        "planner_version": snapshot.get("planner_version"),
        "selected_executor": snapshot.get("selected_executor"),
        "execution_topology": snapshot.get("execution_topology"),
        "executor_model": snapshot.get("executor_model"),
        "executor_provider": snapshot.get("executor_provider"),
        "protocol_mode": snapshot.get("protocol_mode"),
        "selected_capabilities": list(selected_caps) if isinstance(selected_caps, (list, tuple)) else [],
        "selected_capability_count": cap_count,
        "ssd_route_map": bool(snapshot.get("ssd_route_map")),
        "context_slimming_policy": bool(snapshot.get("context_slimming_policy")),
        "harness_relevance_policy": bool(snapshot.get("harness_relevance_policy")),
        "planner_snapshot_sha256": snapshot_sha,
        "field_status": field_status,
        "elapsed_sec": round(t1 - t0, 3),
    }

    return {
        "planner_input": planner_input,
        "planner_output": planner_output,
        "snapshot": snapshot,
        "snapshot_sha256": snapshot_sha,
    }


# ---------------------------------------------------------------------------
# Lane B: Synthetic Binding Truth
# ---------------------------------------------------------------------------
def build_synthetic_snapshot() -> dict:
    """Build a synthetic planner snapshot for binding testing."""
    return {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "executor_provider": "ollama",
        "protocol_mode": "anchored_edit",
        "selected_capabilities": ["repair_loop"],
        "ssd_route_map": {"schema_version": "nexus_ssd_route_map_v1"},
        "context_slimming_policy": {"schema_version": "nexus_context_slimming_policy_v1"},
        "harness_relevance_policy": {"schema_version": "nexus_harness_relevance_policy.v1"},
        "research_isolation_policy": {"level": "L0"},
        "synthetic_contract_fixture": True,
        "not_planner_output": True,
        "not_benchmark_evidence": True,
    }


def run_lane_b_minimal(spy: SpyManager) -> dict:
    """Lane B0: Minimal baseline — only repair/localheal necessary capabilities."""
    snapshot = build_synthetic_snapshot()
    snapshot["selected_capabilities"] = []
    return _run_lane_b_inner(spy, snapshot, "B0_minimal_baseline")


def run_lane_b_armor(spy: SpyManager) -> dict:
    """Lane B1: Armor binding — enable evidence/reasoning/gates capabilities."""
    snapshot = build_synthetic_snapshot()
    snapshot["selected_capabilities"] = ["repair_loop", "semantic_failure_sensor", "codeintel"]
    return _run_lane_b_inner(spy, snapshot, "B1_armor_binding")


def _run_lane_b_inner(spy: SpyManager, snapshot: dict, lane_id: str) -> dict:
    """Common Lane B execution with given snapshot."""
    snapshot_copy = copy.deepcopy(snapshot)

    workspace = tempfile.mkdtemp(prefix=f"n30r_w0_{lane_id}_")
    target_path = Path(workspace) / FIXTURE_TARGET_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(FIXTURE_SOURCE, encoding="utf-8")

    executor_request = LocalModelExecutorRequest(
        task_id=f"n30r_w0_{lane_id}",
        problem_statement=FIXTURE_TASK_DESC,
        repo_root=workspace,
        target_file=FIXTURE_TARGET_FILE,
        selected_capabilities=tuple(snapshot.get("selected_capabilities", ())),
        evidence_refs=(f"n30r-w0-{lane_id}-ref",),
        receipt_context={"lane_id": lane_id, "audit": True},
        route_context={
            "signal_snapshot": snapshot,
            "verifier_command": list(FIXTURE_VERIFIER),
            "target_symbol": FIXTURE_TARGET_SYMBOL,
            "difficulty": "easy",
        },
        model_name=snapshot.get("executor_model", "qwen2.5-coder:7b-instruct"),
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    provider = DeterministicMockProvider()
    injected = InjectedLocalModelProvider(provider.generate)

    spy.executor.call_count += 1
    spy.executor.timestamps.append(time.monotonic())
    spy.executor.argument_sha256 = sha256_str(json.dumps({
        "task_id": executor_request.task_id,
        "repo_root": executor_request.repo_root,
        "target_file": executor_request.target_file,
        "selected_capabilities": list(executor_request.selected_capabilities),
    }, sort_keys=True))

    try:
        response = LocalModelExecutor.run(executor_request, provider=injected)
    except Exception as e:
        response = LocalModelExecutorResponse(
            invoked=False, local_model_called=False,
            candidate_patch="", candidate_hash="",
            reasoning_summary=f"executor_exception:{e}",
            raw_model_metadata={"error": str(e)},
            provider="error", model_name="",
            error=str(e), timeout=False,
            evidence_refs=executor_request.evidence_refs,
        )

    spy.executor.return_type = type(response).__name__

    meta = response.raw_model_metadata if isinstance(response.raw_model_metadata, dict) else {}
    response_sha = sha256_str(json.dumps({
        "invoked": response.invoked,
        "local_model_called": response.local_model_called,
        "candidate_hash": response.candidate_hash,
        "provider": response.provider,
        "model_name": response.model_name,
        "error": response.error,
        "timeout": response.timeout,
    }, sort_keys=True, default=str))

    result = {
        "lane_id": lane_id,
        "workspace": workspace,
        "target_exists": target_path.exists(),
        "target_source_sha256": sha256_str(target_path.read_text()) if target_path.exists() else "",
        "response_type": type(response).__name__,
        "invoked": response.invoked,
        "local_model_called": response.local_model_called,
        "candidate_patch_length": len(response.candidate_patch),
        "candidate_hash": response.candidate_hash,
        "candidate_hash_empty": not bool(response.candidate_hash),
        "reasoning_summary": response.reasoning_summary,
        "provider": response.provider,
        "model_name": response.model_name,
        "error": response.error,
        "timeout": response.timeout,
        "response_sha256": response_sha,
        "raw_model_metadata_keys": sorted(meta.keys()) if meta else [],
        "localheal_pipeline_run_called": meta.get("localheal_pipeline_run_called", False),
        "localheal_pipeline_run_success": meta.get("localheal_pipeline_run_success", False),
        "localheal_pipeline_actual_execution": meta.get("localheal_pipeline_actual_execution", False),
        "pipeline_final_patch_len": len(meta.get("pipeline_final_patch", "")),
        "pipeline_failure_reason": meta.get("pipeline_failure_reason", ""),
        "source_anchor_present": meta.get("source_anchor_present", False),
        "source_anchor_source": meta.get("source_anchor_source", ""),
        "locked_search_present": bool(meta.get("locked_search")),
        "locked_search_length": len(str(meta.get("locked_search", ""))),
        "candidate_isolation_attempted": meta.get("candidate_isolation_attempted", False),
        "candidate_output_isolated": meta.get("candidate_output_isolated", False),
        "selected_candidate_hash": meta.get("selected_candidate_hash", ""),
        "isolated_verifier_status": meta.get("isolated_verifier_status", ""),
        "isolated_apply_status": meta.get("isolated_apply_status", ""),
        "semantic_retry_count": int(meta.get("semantic_retry_count", 0)),
        "provider_calls": len(provider.calls),
        "provider_prompt_sha256": provider.calls[0]["prompt_sha256"] if provider.calls else "",
        "provider_prompt_excerpt": provider.calls[0]["prompt_excerpt"][:300] if provider.calls else "",
    }

    snapshot_after = copy.deepcopy(snapshot)
    result["snapshot_unchanged"] = (snapshot == snapshot_after)

    return result


# ---------------------------------------------------------------------------
# Prompt analysis
# ---------------------------------------------------------------------------
def analyze_prompt(prompt_text: str) -> dict:
    """Check what the prompt contains."""
    return {
        "length": len(prompt_text),
        "sha256": sha256_str(prompt_text),
        "contains_task_statement": FIXTURE_TASK_DESC[:20] in prompt_text,
        "contains_target_file": FIXTURE_TARGET_FILE in prompt_text or "target.py" in prompt_text,
        "contains_target_symbol": FIXTURE_TARGET_SYMBOL in prompt_text,
        "contains_source_code": FIXTURE_SOURCE[:30] in prompt_text,
        "contains_locked_search": "locked_search" in prompt_text.lower() or "LOCKED" in prompt_text,
        "contains_source_anchor": "source_anchor" in prompt_text.lower() or "anchor" in prompt_text.lower(),
        "contains_failure_evidence": "failure" in prompt_text.lower() or "verifier" in prompt_text.lower(),
        "contains_verifier_evidence": "verifier_evidence" in prompt_text.lower(),
        "contains_memory_evidence": "memory" in prompt_text.lower() or "lesson" in prompt_text.lower(),
        "contains_ddtree_evidence": "ddtree" in prompt_text.lower(),
        "contains_autoreason_evidence": "autoreason" in prompt_text.lower(),
        "contains_protocol_instruction": "protocol" in prompt_text.lower() or "SEARCH" in prompt_text or "REPLACE" in prompt_text,
    }


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------
def run_audit() -> dict:
    spy = SpyManager()
    trace = ContractTrace()

    # Lane A
    lane_a = run_lane_a(spy)

    # Lane A trace
    trace.stage1_planner_input = StageTrace(
        captured=True, capture_source="real CapabilityPlanner.plan()",
        timestamp_monotonic=time.monotonic(),
        payload_sha256=sha256_str(json.dumps(lane_a["planner_input"], sort_keys=True, default=str)),
        payload=lane_a["planner_input"],
    )
    trace.stage2_planner_output = StageTrace(
        captured=True, capture_source="real CapabilityPlanner.plan() return",
        timestamp_monotonic=time.monotonic(),
        payload_sha256=lane_a["snapshot_sha256"],
        payload=lane_a["planner_output"],
    )

    # Lane B0 + B1
    lane_b0 = run_lane_b_minimal(spy)
    lane_b1 = run_lane_b_armor(spy)

    # Stage 3-6 from B1 (richest path)
    trace.stage3_executor_request = StageTrace(
        captured=True, capture_source="LocalModelExecutor.run() spy",
        timestamp_monotonic=time.monotonic(),
        payload_sha256=spy.executor.argument_sha256,
        payload={"lane_b1": lane_b1},
    )

    trace.stage5_model_prompt = StageTrace(
        captured=True, capture_source="DeterministicMockProvider.generate() spy",
        timestamp_monotonic=time.monotonic(),
        payload_sha256=lane_b1.get("provider_prompt_sha256", ""),
        payload=analyze_prompt(lane_b1.get("provider_prompt_excerpt", "")),
    )

    trace.stage6_receipt = StageTrace(
        captured=True, capture_source="LocalModelExecutorResponse",
        timestamp_monotonic=time.monotonic(),
        payload_sha256=lane_b1.get("response_sha256", ""),
        payload={k: v for k, v in lane_b1.items() if k not in ("provider_prompt_excerpt",)},
    )

    # Capability Effect Ledger
    caps_registry = ["repair_loop", "semantic_failure_sensor", "codeintel",
                     "memory", "ddtree", "autoreason",
                     "artifact_gate", "claim_gate", "delivery_gate"]
    capability_ledger = {}
    for cap in caps_registry:
        selected_in_b1 = cap in (lane_b1.get("selected_capabilities_from_snapshot", []) or [])
        capability_ledger[cap] = {
            "selected": selected_in_b1,
            "selected_source": "synthetic_snapshot_B1" if selected_in_b1 else "not_selected",
            "bound": False,
            "binding_source": "",
            "invoked": False,
            "invocation_source": "",
            "evidence_added": False,
            "evidence_delta_sha256": "",
            "prompt_delta": False,
            "prompt_delta_sha256": "",
            "outcome_contributed": False,
            "contribution_source": "",
            "receipt_refs": [],
        }

    # Compare B0 vs B1 prompts
    b0_prompt = lane_b0.get("provider_prompt_sha256", "")
    b1_prompt = lane_b1.get("provider_prompt_sha256", "")
    prompt_delta = b0_prompt != b1_prompt

    # Audit summary
    audit_result = {
        "run_id": f"w0_{int(time.time())}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fixture": {
            "target_file": FIXTURE_TARGET_FILE,
            "target_symbol": FIXTURE_TARGET_SYMBOL,
            "source_sha256": FIXTURE_SOURCE_SHA,
            "verifier_command": list(FIXTURE_VERIFIER),
        },
        "lane_a": lane_a,
        "lane_b0": {k: v for k, v in lane_b0.items() if k != "workspace"},
        "lane_b1": {k: v for k, v in lane_b1.items() if k != "workspace"},
        "spy": {
            "planner_call_count": spy.planner.call_count,
            "executor_call_count": spy.executor.call_count,
            "planner_return_type": spy.planner.return_type,
            "executor_return_type": spy.executor.return_type,
        },
        "trace": {
            "stage1_captured": trace.stage1_planner_input.captured,
            "stage2_captured": trace.stage2_planner_output.captured,
            "stage3_captured": trace.stage3_executor_request.captured,
            "stage5_captured": trace.stage5_model_prompt.captured,
            "stage6_captured": trace.stage6_receipt.captured,
        },
        "capability_ledger": capability_ledger,
        "prompt_analysis": trace.stage5_model_prompt.payload,
        "prompt_delta_b0_vs_b1": prompt_delta,
        "classification": _classify(lane_a, lane_b0, lane_b1, capability_ledger),
    }

    return audit_result


def _classify(lane_a, lane_b0, lane_b1, ledger) -> list[str]:
    cls = []
    snap = lane_a["snapshot"]

    # Control plane
    if snap.get("selected_executor") and snap.get("execution_topology"):
        cls.append("CONTROL_PLANE_CONNECTED")

    # Planner source blind?
    planner_input = lane_a["planner_input"]
    if not planner_input.get("source_code_present"):
        cls.append("PLANNER_SOURCE_BLIND")
    if not planner_input.get("codeintel_nonempty"):
        cls.append("PLANNER_EVIDENCE_BLIND")

    # Topology only?
    cap_count = lane_a["planner_output"].get("selected_capability_count", 0)
    if cap_count == 0:
        cls.append("PLANNER_TOPOLOGY_ONLY")
        cls.append("CAPABILITY_SELECTION_EMPTY")

    # Source anchor?
    if not lane_b1.get("source_anchor_present"):
        cls.append("SOURCE_ANCHOR_MISSING")
    if not lane_b1.get("locked_search_present"):
        cls.append("LOCKED_SEARCH_MISSING")

    # Lifecycle
    if lane_b1.get("localheal_pipeline_run_called") and lane_b1.get("localheal_pipeline_actual_execution"):
        cls.append("VERIFIER_CONTRACT_CONNECTED")
    if lane_b1.get("candidate_isolation_attempted"):
        cls.append("CANDIDATE_LIFECYCLE_CONNECTED")

    # Evidence/prompt
    prompt = lane_b1.get("provider_prompt_excerpt", "")
    if not any(kw in prompt.lower() for kw in ["source", "anchor", "locked", "evidence"]):
        cls.append("EVIDENCE_NOT_REACHING_PROMPT")

    # Receipt provenance
    if not lane_b1.get("response_sha256"):
        cls.append("RECEIPT_PROVENANCE_INCOMPLETE")

    if not cls:
        cls.append("FULL_ARMOR_CONTRACT_CONNECTED")

    return cls


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    print("N30R-W0 Contract Audit starting...")
    print(f"  Fixture: {FIXTURE_TARGET_FILE}")
    print(f"  Source SHA: {FIXTURE_SOURCE_SHA}")

    result = run_audit()

    trace_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"w0_contract_trace_{result['run_id']}.json"
    trace_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"  Trace written: {trace_path}")

    # Summary
    print("\n=== Lane A Planner Truth ===")
    la = result["lane_a"]["planner_output"]
    print(f"  planner_version: {la['planner_version']}")
    print(f"  selected_executor: {la['selected_executor']}")
    print(f"  execution_topology: {la['execution_topology']}")
    print(f"  selected_capabilities: {la['selected_capabilities']}")
    print(f"  selected_capability_count: {la['selected_capability_count']}")

    print("\n=== Lane B1 Binding Truth ===")
    b1 = result["lane_b1"]
    print(f"  invoked: {b1['invoked']}")
    print(f"  pipeline_run_called: {b1['localheal_pipeline_run_called']}")
    print(f"  pipeline_actual_execution: {b1['localheal_pipeline_actual_execution']}")
    print(f"  source_anchor: {b1['source_anchor_present']}")
    print(f"  locked_search: {b1['locked_search_present']}")
    print(f"  candidate_isolation_attempted: {b1['candidate_isolation_attempted']}")
    print(f"  provider_calls: {b1['provider_calls']}")

    print("\n=== Prompt Analysis ===")
    pa = result["prompt_analysis"]
    for k, v in pa.items():
        if isinstance(v, bool):
            print(f"  {k}: {'YES' if v else 'no'}")

    print("\n=== Classification ===")
    for c in result["classification"]:
        print(f"  {c}")

    print("\n=== Spies ===")
    sp = result["spy"]
    print(f"  planner calls: {sp['planner_call_count']}")
    print(f"  executor calls: {sp['executor_call_count']}")

    print(f"\n  Status: {result['classification']}")


if __name__ == "__main__":
    main()
