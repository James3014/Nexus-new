#!/usr/bin/env python3
"""Z1 — Nexus Capability Binding Audit script."""
import json
import os
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "z1_capability_binding_audit_v0"


def main():
    print("Running Z1 Capability Binding Audit...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Define Capability Binding Matrix
    matrix = {
        "CodeIntel": {
            "status": "bypassed",
            "expected_role": "Generate nodes/edges based on dynamic AST graph & symbol ownership.",
            "actual_role": "Uses static heuristic search and string matching in native_evidence_packet.py.",
            "gap_details": "No call to Nexus native CodeIntel symbol mapping or impact radius estimation."
        },
        "Memory_LanceDB": {
            "status": "stubbed",
            "expected_role": "Retrieve prior failure lessons, positive action weights, and deduplicate patterns.",
            "actual_role": "Hardcoded heuristic rule checks based on task types in native_evidence_packet.py.",
            "gap_details": "No LanceDB retrieval calls. Learning closure jsonl is written but not queried back."
        },
        "Autoreason": {
            "status": "bypassed",
            "expected_role": "Semantic plausibility scoring of candidates prior to verification.",
            "actual_role": "None. Proposers directly output patches, checked only by syntax parser and verifier.",
            "gap_details": "Autoreason has no influence on local candidate selection or ranking."
        },
        "DDTree": {
            "status": "bypassed",
            "expected_role": "Prune invalid repair decision branches, reduce proposer model call overhead.",
            "actual_role": "No branch pruning or proactive path reduction.",
            "gap_details": "Proposers generate max_candidates blindly. Pruning receipt is absent."
        },
        "Belief": {
            "status": "partially_connected",
            "expected_role": "Maintain subjective confidence probabilities, drive uncertainty trigger and escalation.",
            "actual_role": "Hardcoded trigger weight threshold checks (e.g. w1 score).",
            "gap_details": "Uncertainty triggers are static heuristic matrices; does not bind dynamic Belief state."
        },
        "Artifact_Claim_Delivery": {
            "status": "partially_connected",
            "expected_role": "Enforce verifier/sandbox receipt checks, prevent false claims, separate pass/fail/gated.",
            "actual_role": "Checks compliance and role contracts in runbook_compliance.py.",
            "gap_details": "Claim format is local-only; not integrated with Nexus global delivery receipts."
        },
        "Sandbox_Replay": {
            "status": "connected",
            "expected_role": "Run isolated verification, cache replays to prevent environment contamination.",
            "actual_role": "Utilizes linear_replay_runner.py and workspace_provision.py for verification.",
            "gap_details": "No major gap. Multi-file/multi-anchor is safely verified in isolated workspace."
        },
        "Ultra_Review": {
            "status": "stubbed",
            "expected_role": "Perform ghost regression checks and safety/security audits for multi-file edits.",
            "actual_role": "Abstains or requires manual owner approval flag.",
            "gap_details": "Automatic security and broad-rewrite safety audit report is not generated."
        },
        "Learning_Closure_MetaOpt": {
            "status": "partially_connected",
            "expected_role": "Write successes/failures back to learn/ closure matrices for meta-opt hyper-tuning.",
            "actual_role": "Writes jsonl logs to learning_closure.jsonl after execution.",
            "gap_details": "Feedback data is offline; not consumed dynamically by Selector/Router weight tuning."
        },
        "Swarm_Drone": {
            "status": "bypassed",
            "expected_role": "Spawn lightweight diagnostic drones to gather evidence for hard tasks.",
            "actual_role": "Heuristic single-threaded loop.",
            "gap_details": "No swarm partition or drone-based background evidence gathering."
        }
    }

    # 2. Derive connected, bypassed, and stubbed list
    connected = [k for k, v in matrix.items() if v["status"] == "connected"]
    bypassed = [k for k, v in matrix.items() if v["status"] == "bypassed"]
    stubbed = [k for k, v in matrix.items() if v["status"] in ["stubbed", "partially_connected"]]

    # 3. Define route call graph topology
    route_call_graph = {
        "nodes": [
            {"id": "uncertainty_trigger", "type": "route_gate"},
            {"id": "evidence_builder", "type": "context_construction"},
            {"id": "proposers", "type": "portfolio_llm"},
            {"id": "action_parser", "type": "grammar_check"},
            {"id": "applier", "type": "code_modification"},
            {"id": "sandbox_verifier", "type": "execution_verification"},
            {"id": "receipt_writer", "type": "governance_audit"}
        ],
        "edges": [
            {"source": "uncertainty_trigger", "target": "evidence_builder", "flow": "uncertainty_checked"},
            {"source": "evidence_builder", "target": "proposers", "flow": "context_supplied"},
            {"source": "proposers", "target": "action_parser", "flow": "raw_output"},
            {"source": "action_parser", "target": "applier", "flow": "parsed_action"},
            {"source": "applier", "target": "sandbox_verifier", "flow": "modified_source"},
            {"source": "sandbox_verifier", "target": "receipt_writer", "flow": "run_evidence"}
        ]
    }

    # 4. Receipt Gap Report
    receipt_gap_report = {
        "gaps": [
            {"field": "evidence_graph_provenance", "severity": "medium", "reason": "Nodes/edges lack real AST database hashes."},
            {"field": "prior_lesson_provenance", "severity": "high", "reason": "No LanceDB retrieval signature in receipt."},
            {"field": "advisory_scores", "severity": "low", "reason": "Autoreason semantic checks missing from final log."},
            {"field": "delivery_claim_signature", "severity": "medium", "reason": "Receipt lacks secure global delivery gate sign-off."}
        ]
    }

    # Write files
    with open(OUTPUT_DIR / "capability_binding_matrix.json", "w") as f:
        json.dump(matrix, f, indent=2)

    with open(OUTPUT_DIR / "connected_capabilities.json", "w") as f:
        json.dump(connected, f, indent=2)

    with open(OUTPUT_DIR / "bypassed_capabilities.json", "w") as f:
        json.dump(bypassed, f, indent=2)

    with open(OUTPUT_DIR / "stubbed_capabilities.json", "w") as f:
        json.dump(stubbed, f, indent=2)

    with open(OUTPUT_DIR / "route_call_graph.json", "w") as f:
        json.dump(route_call_graph, f, indent=2)

    with open(OUTPUT_DIR / "receipt_gap_report.json", "w") as f:
        json.dump(receipt_gap_report, f, indent=2)

    print("Z1 Capability Binding Audit completed successfully.")


if __name__ == "__main__":
    main()
