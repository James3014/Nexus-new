from __future__ import annotations

import os
import tempfile
import shutil
from unittest import mock

from nexus.contracts.hybrid_route import RouteMode, Authority, VerifierResult
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.capability_planner import CapabilityPlanner


# #1924: controls come from a real CapabilityPlanner.plan() passed through build_execution_plan(),
# whose planner-bound route_context must not be edited. Isolated solve is reachable only once the
# planner itself grants it (quarantined until then).
def _planned_controls(**fixture_controls: object) -> dict:
    plan = CapabilityPlanner().plan(task_desc="fix code", task_type="repair", route={"local_enabled": True})
    controls = dict(build_execution_plan(plan).executor_controls)
    assert controls["route_context"]["signal_snapshot"]["planner_version"] == "capability_planner_v1"
    return {**controls, **fixture_controls}


def test_abc_local_heal_full_isolated_solve_seam() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
    }):
        with tempfile.TemporaryDirectory() as src_root:
            test_file = "f.py"
            src_path = os.path.join(src_root, test_file)
            with open(src_path, "w", encoding="utf-8") as f:
                f.write("print('hello')\n")
                
            diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
            
            def mock_gen(req) -> str:
                return f"```diff\n{diff}```"
                
            request = LocalHealCapabilityRequest(
                task_id="t_abc",
                problem_statement="fix code",
                evidence_refs=("ref1",),
                executor_controls=_planned_controls(
                    source_root=src_root,
                    target_file=test_file,
                    target_symbol="print",
                    locked_search="print('hello')",
                    verifier_command=["python3", "-c", "import os; assert os.path.exists('f.py')"],
                    work_dir="",
                    candidate_generate_fn=mock_gen,
                ),
                dry_run=False,
            )
            
            response = LocalHealCapabilityAdapter.run(request)
            
            assert response.invoked is True
            assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
            assert response.hybrid_route.local_model_called is True
            
            receipt_adapter = LocalHealReceiptAdapter()
            
            receipt1 = receipt_adapter.build(claim_verified=True, payload=response.capability_payload)
            assert receipt1.name == "local_heal"
            assert receipt1.invoked is True
            assert receipt1.gate_passed is True
            assert receipt1.evidence_present is True
            # #453 closure (ADVISORY_ONLY_FAIL_CLOSED): adapter payloads cannot mint verifier
            # authority, so even a verified claim does not contribute an outcome here.
            assert receipt1.outcome_contributed is False
            
            receipt2 = receipt_adapter.build(claim_verified=False, payload=response.capability_payload)
            assert receipt2.gate_passed is True
            assert receipt2.outcome_contributed is False
            
            workspace_path = response.hybrid_route.metadata.get("workspace_path", "")
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)


def test_abc_local_heal_full_isolated_solve_with_fail_closed_guard_enabled() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
        "NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE": "1",
    }):
        with tempfile.TemporaryDirectory() as src_root:
            test_file = "f.py"
            src_path = os.path.join(src_root, test_file)
            with open(src_path, "w", encoding="utf-8") as f:
                f.write("print('hello')\n")
                
            diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
            
            def mock_gen(req) -> str:
                return f"```diff\n{diff}```"
                
            request = LocalHealCapabilityRequest(
                task_id="t_abc_guard",
                problem_statement="fix code",
                evidence_refs=("ref1",),
                executor_controls=_planned_controls(
                    source_root=src_root,
                    target_file=test_file,
                    target_symbol="print",
                    locked_search="print('hello')",
                    verifier_command=["python3", "-c", "import os; assert os.path.exists('f.py')"],
                    work_dir="",
                    candidate_generate_fn=mock_gen,
                ),
                dry_run=False,
            )
            
            response = LocalHealCapabilityAdapter.run(request)
            
            assert response.invoked is True
            assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
            assert response.hybrid_route.public_claim_allowed is False
            assert response.hybrid_route.production_ready is False
            
            workspace_path = response.hybrid_route.metadata.get("workspace_path", "")
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)
