"""Production Canary Runner — Production dispatch for local/online capability tasks.

Pure production module — imports only nexus.* production code.
DO NOT import tests.* from this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.services.capability_registry import LOCAL_STAGE_CAPABILITIES
from nexus.services.product_capability_closure_harness import ClosureTaskSpec


def run_production_canary(task: ClosureTaskSpec) -> dict[str, Any]:
    from nexus.services.product_capability_canary_helper import run_canary_mainchain
    
    result = run_canary_mainchain(
        task.capability,
        positive=True,
        task_id_override=task.task_id,
        task_spec=task,
    )

    
    if task.origin == "online":
        evidence_payload = {
            "schema": "nexus.product_capability_online_native_evidence.v1",
            "capability": task.capability,
            "mainchain_result": result,
            "expected_effect": dict(task.expected_effect),
            "public_claim_allowed": False,
        }
        evidence_root = Path(str(task.fixture["workspace_root"])) / ".nexus" / "closure_evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_root / f"online-{task.capability}.json"
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result
    else:
        # Local origin dispatch
        LOCAL_NATIVE = ("local_model_executor", "repair_loop")
        if task.capability in LOCAL_NATIVE:
            response_path = (
                Path("/tmp/nexus_family_canary")
                / task.task_id
                / ".nexus"
                / "reports"
                / "local_assist"
                / task.task_id
                / "response.json"
            )
            receipt_path = response_path.with_name("execution_receipt.json")
            response = json.loads(response_path.read_text(encoding="utf-8")) if response_path.exists() else {}
            candidate = dict(response.get("candidate_summary") or {})
            local_execution = {
                "model_called": response.get("local_model_invoked") is True,
                "output_delivered": response.get("output_delivered") is True,
                "candidate_isolated": candidate.get("isolation_status") == "isolated",
                "candidate_hash": candidate.get("model_candidate_hash") or "",
                "selected_hash": candidate.get("selected_candidate_hash") or "",
                "applied_hash": candidate.get("applied_patch_hash") or "",
                "provider_family": response.get("provider") or "ollama",
                "model_name": (response.get("resolved_models") or ["qwen2.5-coder:7b-instruct"])[0],
                "loop_entered": task.capability == "repair_loop",
            }
        else:
            response = {}
            local_execution = {}

        evidence_payload = {
            "schema": "nexus.product_capability_local_native_evidence.v1",
            "task_id": task.task_id,
            "capability": task.capability,
            "mainchain_status": result.get("status"),
            "candidate_hash": local_execution.get("candidate_hash") or "",
            "verifier_status": "pass" if result.get("status") in ("OK", "SUCCEEDED") else "fail",
            "public_claim_allowed": False,
        }
        evidence_root = Path(str(task.fixture["workspace_root"])) / ".nexus" / "closure_evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_root / f"local-{task.capability}.json"
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result
