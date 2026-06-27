from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 自帶 Path 載入
repo_root = str(Path(__file__).resolve().parents[2])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled local solve fixture lane")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--target-file", required=True)
    parser.add_argument("--target-symbol", required=True)
    parser.add_argument("--locked-search", required=True)
    parser.add_argument("--problem-statement", default="fix code")
    parser.add_argument("--verifier-command-json", default="[]")
    parser.add_argument("--model-output-file", required=False)
    parser.add_argument("--provider-mode", choices=["injected", "ollama"], default="injected")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--evidence-ref", action="append")
    parser.add_argument("--no-evidence", action="store_true")
    
    args = parser.parse_args()
    
    model_output = ""
    if args.provider_mode == "injected":
        if not args.model_output_file:
            print("Error: --model-output-file is required for injected provider mode")
            return 1
        try:
            model_output = Path(args.model_output_file).read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading model output file: {e}")
            return 1
        
    try:
        verifier_cmd = json.loads(args.verifier_command_json)
        if not isinstance(verifier_cmd, list):
            verifier_cmd = []
    except Exception:
        verifier_cmd = []
        
    env_updates = {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
    }
    
    controls = {
        "source_root": args.source_root,
        "target_file": args.target_file,
        "target_symbol": args.target_symbol,
        "locked_search": args.locked_search,
        "verifier_command": verifier_cmd,
        "work_dir": "",
    }
    
    if args.provider_mode == "injected":
        controls["candidate_generate_fn"] = lambda req: model_output
    else:
        env_updates["NEXUS_LOCAL_MODEL_PROVIDER"] = "ollama"
        if "NEXUS_LOCAL_MODEL_NAME" not in os.environ:
            env_updates["NEXUS_LOCAL_MODEL_NAME"] = "qwen2.5-coder"
            
    if args.no_evidence:
        evidence_refs = ()
    else:
        evidence_refs = tuple(args.evidence_ref) if args.evidence_ref else ("fixture-ref",)

    request = LocalHealCapabilityRequest(
        task_id=args.task_id,
        problem_statement=args.problem_statement,
        evidence_refs=evidence_refs,
        executor_controls=controls,
    )
    
    from unittest.mock import patch
    with patch.dict(os.environ, env_updates):
        response = LocalHealCapabilityAdapter.run(request)
    
    from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter
    receipt_adapter = LocalHealReceiptAdapter()
    receipt = receipt_adapter.build(claim_verified=True, payload=response.capability_payload)
    
    result_data = {
        "task_id": response.task_id,
        "invoked": response.invoked,
        "route_mode": response.hybrid_route.route_mode.value,
        "gate_passed": receipt.gate_passed,
        "fallback_block_reason": response.hybrid_route.fallback_block_reason,
        "public_claim_allowed": response.hybrid_route.public_claim_allowed,
        "production_ready": response.hybrid_route.production_ready,
        "metadata": response.capability_payload.get("metadata", {}),
    }
    
    try:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
    except Exception as e:
        print(f"Error writing output json: {e}")
        return 1
        
    workspace_path = response.hybrid_route.metadata.get("workspace_path", "")
    if workspace_path and os.path.exists(workspace_path):
        import shutil
        try:
            shutil.rmtree(workspace_path)
        except Exception:
            pass
            
    return 0


if __name__ == "__main__":
    sys.exit(main())
