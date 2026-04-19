#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def run_replay(evidence_path: str, allow_no_replay: bool = False):
    p = Path(evidence_path)
    if not p.exists():
        return {"status": "FAIL", "reason": "EVIDENCE_NOT_FOUND"}
    
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return {"status": "FAIL", "reason": f"PARSE_ERROR: {e}"}

    bundle = data.get("evidence_bundle", {})
    test_artifacts = bundle.get("test_artifacts", [])
    
    if not test_artifacts:
        if allow_no_replay:
            return {"status": "PARTIAL", "reason": "NO_TEST_ARTIFACTS_ALLOWED"}
        else:
            return {"status": "FAIL", "reason": "NO_TEST_ARTIFACTS_REJECTED"}
            
    # In a real scenario, this would re-run the tests or verify their logs/hashes.
    # For now, we strictly enforce existence.
    return {"status": "PASS", "replay_count": len(test_artifacts)}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    parser.add_argument("--allow-no-replay", action="store_true", default=False)
    args = parser.parse_args()
    
    result = run_replay(args.evidence, args.allow_no_replay)
    print(json.dumps(result))
    sys.exit(0 if result["status"] in ["PASS", "PARTIAL"] else 1)
