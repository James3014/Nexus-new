#!/usr/bin/env python3
import json
import sys
import subprocess
from pathlib import Path

# Ensure nexus package is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nexus.core.hallucination_guard import HallucinationGuard

def verify_evidence(evidence_path: str, allow_no_replay: bool = False):
    p = Path(evidence_path)
    if not p.exists():
        return {"status": "REJECTED", "reason": "MISSING_EVIDENCE"}

    # 1. Run Replay Runner
    cmd = ["python3", "scripts/ops/replay_runner.py", evidence_path]
    if allow_no_replay:
        cmd.append("--allow-no-replay")
    
    replay_res = subprocess.run(cmd, capture_output=True, text=True)
    replay_data = json.loads(replay_res.stdout) if replay_res.stdout else {"status": "FAIL"}

    # 2. Hallucination Index Analysis
    guard = HallucinationGuard()
    evidence_data = json.loads(p.read_text())
    analysis = guard.analyze(evidence_data.get("final_response", ""), evidence_data.get("evidence_bundle", {}))

    # 3. Final Verdict Alignment
    status = analysis["status"]
    if replay_data["status"] == "FAIL":
        status = "REJECTED"
        analysis["verdict"] = "🔴 重做 (Replay Failed)"
        analysis["score"] = 10.0

    return {
        "status": status,
        "overall_trust": "HIGH" if status == "VERIFIED" else "LOW",
        "replay": replay_data,
        "hallucination_index": analysis
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    parser.add_argument("--allow-no-replay", action="store_true", default=False)
    args = parser.parse_args()
    
    result = verify_evidence(args.evidence, args.allow_no_replay)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "VERIFIED" else 1)
