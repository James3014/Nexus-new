#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_shadow import S2TShadowRecorder

def main():
    trace_file = Path(".nexus/metrics/skill_outcome_events.jsonl")
    ab_eval_file = Path(".nexus/metrics/s2t_ab_eval_rows.jsonl")
    
    print(f"Injecting shadow events to {trace_file.absolute()}")
    print(f"Injecting ab_eval rows to {ab_eval_file.absolute()}")
    
    recorder = S2TShadowRecorder(trace_path=trace_file)
    
    ab_rows = []
    for i in range(35):
        candidates = [
            S2TCandidate(
                candidate_id=f"cand-fail-{i}",
                source="first_pass",
                content_ref=f".nexus/reports/s2t/cand-fail-{i}.json",
                static_score=0.5,
                selector_score=0.6,
                verifier_result="fail",
                risk_flags=["missing_test_evidence"],
            ),
            S2TCandidate(
                candidate_id=f"cand-pass-{i}",
                source="repair_pass",
                content_ref=f".nexus/reports/s2t/cand-pass-{i}.json",
                static_score=0.8,
                selector_score=0.9,
                verifier_result="pass",
                evidence_refs=[f"tests/test_target_{i}.py"],
            ),
        ]
        
        recorder.record(
            task_id=f"sim-task-{i}",
            run_id=f"sim-run-{i}",
            model="gemini-3-flash-preview",
            phase="R",
            risk_tier="medium",
            candidate_set_id=f"candset-{i}",
            candidates=candidates,
            original_final_candidate_id=f"cand-fail-{i}",
            verifier_name="pytest",
            verifier_result="pass",
            verifier_evidence_ref=f".nexus/reports/pytest_{i}.json",
        )
        
        # Build matching ab_eval row
        ab_rows.append({
            "run_eligible": True,
            "original_top1_candidate_id": f"cand-fail-{i}",
            "s2t_selected_candidate_id": f"cand-pass-{i}",
            "original_top1_verified": False,
            "s2t_selected_verified": True,
            "time_to_verified": 10.0,
            "public_cost_evidence": True,
            "trust_mismatch": False
        })
        
    # Write ab_eval_rows
    ab_eval_file.parent.mkdir(parents=True, exist_ok=True)
    with ab_eval_file.open("w", encoding="utf-8") as f:
        for row in ab_rows:
            f.write(json.dumps(row) + "\n")
            
    print("✅ Successfully generated 35 shadow events and 35 ab_eval rows.")

if __name__ == "__main__":
    main()
