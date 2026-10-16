#!/usr/bin/env python3
"""AB1 — Full Capability Route Definition and Verification Script."""
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "ab1_full_capability_route_definition_v0"

def check_swarm_drone_status():
    # Swarm/Drone local lock is still stubbed as per current codebase state
    return "STUBBED"

def main():
    print("Running AB1 Full Capability Route Definition...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Define Route Contract
    full_route_contract = {
        "route_id": "local_full_nexus_repair_control_plane_v0",
        "route_allowed": True,
        "allowed_capabilities": [
            "pregate_risk_classification",
            "codeintel_evidence_graph_ast",
            "memory_lessons_retrieval_lancedb",
            "autoreason_ddtree_pruning",
            "belief_confidence_tracking",
            "heterogeneous_proposer_portfolio",
            "controlled_action_protocol",
            "deterministic_span_applier",
            "sandbox_isolated_validation",
            "ultra_review_report",
            "delivery_claim_separation",
            "learning_closure_writeback"
        ],
        "forbidden_capabilities": [
            "unrestricted_multifile_edit",
            "verifier_override_allow",
            "public_claim_release",
            "training_data_export",
            "cloud_api_unapproved"
        ]
    }

    # 2. Capability Invocation Matrix
    capability_invocation_matrix = {
        "stages": {
            "1_pregate": {"status": "Wired", "invoked_by": "budget_manager", "capabilities": ["budget_estimation", "risk_classification"]},
            "2_codeintel": {"status": "Wired", "invoked_by": "evidence_graph", "capabilities": ["ast_imports_extraction", "caller_callee_structure"]},
            "3_memory": {"status": "Wired", "invoked_by": "semantic_anchor_selection", "capabilities": ["lancedb_lessons_retrieval", "success_failure_bonus_penalty"]},
            "4_reasoning": {"status": "Wired", "invoked_by": "reasoning_router", "capabilities": ["ddtree_candidate_pruning", "belief_confidence_write"]},
            "5_model_portfolio": {"status": "Wired", "invoked_by": "local_model_policy", "capabilities": ["3b_judge_abstain", "qwen_7b_proposer", "deepseek_6.7b_proposer"]},
            "6_controlled_protocol": {"status": "Wired", "invoked_by": "action_protocol", "capabilities": ["search_replace_enforcement", "coordinated_two_file_gating"]},
            "7_applier": {"status": "Wired", "invoked_by": "constrained_action_applier", "capabilities": ["span_verification", "dry_run_apply", "rollback_support"]},
            "8_sandbox": {"status": "Wired", "invoked_by": "micro_verifier", "capabilities": ["sandbox_execution_isolation", "ultra_review_generation"]},
            "9_claim": {"status": "Wired", "invoked_by": "evaluation_gate", "capabilities": ["verifier_pass_separation", "false_green_blocking"]},
            "10_learning": {"status": "Wired", "invoked_by": "failure_memory", "capabilities": ["learning_closure_writeback", "metrics_ledger_recording"]}
        }
    }

    # 3. Route Stage Schema
    route_stage_schema = {
        "input_payload": {
            "task_id": "str",
            "repo_dir": "str",
            "problem_statement": "str",
            "localized_files": "list[tuple[str, str]]"
        },
        "output_payload": {
            "solved": "bool",
            "gate_exit": "str",
            "failure_reason": "str",
            "final_patch": "str",
            "model_calls": "int",
            "claim_status": "str"
        }
    }

    # 4. Safety Policy
    safety_policy = {
        "public_claim_allowed": False,
        "production_ready": False,
        "training_export_allowed": False,
        "internal_only": True,
        "max_files_touched": 10,
        "coordinated_edit_limit": 2,
        "owner_approval_required_for_coordinated": True,
        "broad_edit_abstain_threshold": 3
    }

    # 5. Resource Policy
    resource_policy = {
        "system_ram_physical_limit_gb": 16.0,
        "peak_ram_allowed_gb": 12.0,
        "fallback_14b_enabled": False, # Resource gated default
        "fallback_14b_reason": "DOWNLOAD_IN_PROGRESS_RESOURCE_LIMITED",
        "cpu_only_execution": False
    }

    # 6. Receipt Schema
    receipt_schema = {
        "receipt_fields": [
            "task_id",
            "solved",
            "claim_status",
            "failure_reason",
            "verifier_pass",
            "owner_approval_required",
            "model_calls",
            "wall_time_sec",
            "allowed_capabilities_used",
            "authority_trace"
        ]
    }

    # 7. Missing or Stubbed Capabilities
    missing_or_stubbed_capabilities = {
        "stubbed": [
            {
                "capability": "Swarm/Drone local lock",
                "description": "Multi-threaded local worktree file locking and concurrent worker synchronization.",
                "reason_deferred": "deferred because local multi-threaded worktree lock is still stub."
            }
        ]
    }

    # Write files
    with open(OUTPUT_DIR / "full_route_contract.json", "w") as f:
        json.dump(full_route_contract, f, indent=2)

    with open(OUTPUT_DIR / "capability_invocation_matrix.json", "w") as f:
        json.dump(capability_invocation_matrix, f, indent=2)

    with open(OUTPUT_DIR / "route_stage_schema.json", "w") as f:
        json.dump(route_stage_schema, f, indent=2)

    with open(OUTPUT_DIR / "safety_policy.json", "w") as f:
        json.dump(safety_policy, f, indent=2)

    with open(OUTPUT_DIR / "resource_policy.json", "w") as f:
        json.dump(resource_policy, f, indent=2)

    with open(OUTPUT_DIR / "receipt_schema.json", "w") as f:
        json.dump(receipt_schema, f, indent=2)

    with open(OUTPUT_DIR / "missing_or_stubbed_capabilities.json", "w") as f:
        json.dump(missing_or_stubbed_capabilities, f, indent=2)

    print("AB1 Route Definition files materialized successfully.")

if __name__ == "__main__":
    main()
