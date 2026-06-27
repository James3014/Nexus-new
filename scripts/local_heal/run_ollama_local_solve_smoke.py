#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from nexus.services.local_heal.capability_adapter import build_local_model_provider_from_env
from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ollama Local Solve Smoke Runner")
    parser.add_argument("--task-id", default="smoke-t1")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--problem-statement", default="Fix formatting in main.py")
    parser.add_argument("--target-file", default="main.py")
    parser.add_argument("--verifier-command", default="python3 -c 'print(1)'")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--target-symbol", default="")
    parser.add_argument("--locked-search", default="")
    args = parser.parse_args()
    
    smoke_enable = os.environ.get("NEXUS_LOCAL_SOLVE_SMOKE_ENABLE") == "1"
    model_allowed = os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
    provider = os.environ.get("NEXUS_LOCAL_MODEL_PROVIDER")
    model_name = os.environ.get("NEXUS_LOCAL_MODEL_NAME")
    
    if not (smoke_enable and model_allowed and provider == "ollama" and model_name):
        res = {
            "model_called": False,
            "parser_status": "blocked",
            "patch_apply_status": "blocked",
            "verifier_status": "blocked",
            "route_mode": "local_only_blocked",
            "gate_passed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "evidence_refs": [],
            "fallback_block_reason": "env_variables_disabled_for_real_ollama",
        }
        print(json.dumps(res, indent=2))
        return 0
        
    provider_inst = build_local_model_provider_from_env(os.environ, {}, "")
    prompt = f"Problem: {args.problem_statement}\nTarget file: {args.target_file}\nPlease output a unified diff."
    
    req_obj = LocalModelProviderRequest(
        task_id=args.task_id,
        prompt=prompt,
        evidence_refs=("smoke-ref",),
        model_name=model_name,
    )
    provider_res = provider_inst.generate(req_obj)
    raw_output = provider_res.output_text
    error = provider_res.error
    
    if error or not raw_output:
        res = {
            "model_called": True,
            "parser_status": "blocked",
            "patch_apply_status": "blocked",
            "verifier_status": "blocked",
            "route_mode": "local_only_blocked",
            "gate_passed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "evidence_refs": [],
            "fallback_block_reason": f"model_error: {error}" if error else "empty_model_output",
        }
        print(json.dumps(res, indent=2))
        return 0
        
    verifier_cmd = tuple(args.verifier_command.split())
    
    locked_search = args.locked_search
    if not locked_search:
        target_path = os.path.join(args.source_root, args.target_file)
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    locked_search = f.read()
            except Exception:
                pass

    request = IsolatedLocalSolveRequest(
        task_id=args.task_id,
        source_root=args.source_root,
        problem_statement=args.problem_statement,
        evidence_refs=("smoke-ref",),
        model_output=raw_output,
        verifier_command=verifier_cmd,
        work_dir=args.work_dir,
        local_model_called=True,
        mutation_allowed=True,
        verifier_allowed=True,
        target_file=args.target_file,
        target_symbol=args.target_symbol,
        locked_search=locked_search,
    )
    
    response = run_isolated_local_solve_loop(request)
    
    receipt = {
        "model_called": True,
        "parser_status": response.patch_envelope.parser_status,
        "patch_apply_status": response.apply_receipt.patch_apply_status,
        "verifier_status": response.verifier_receipt.verifier_status,
        "route_mode": response.hybrid_route.route_mode.value,
        "gate_passed": response.capability_payload.get("gate_passed", False),
        "public_claim_allowed": response.hybrid_route.public_claim_allowed,
        "production_ready": response.hybrid_route.production_ready,
        "evidence_refs": list(request.evidence_refs),
        "fallback_block_reason": response.hybrid_route.fallback_block_reason,
    }
    
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
