#!/usr/bin/env python3
import importlib.util
import json
import sys
from pathlib import Path

# Reuse the allowlisted, shell-free replay implementation (single source of truth).
# Load the module file directly: importing the `nexus.delivery` package would pull in
# pydantic, and this script runs under a bare python3 (stdlib only) in the delivery gate.
REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "nexus_delivery_replay_runner", REPO_ROOT / "nexus" / "delivery" / "replay_runner.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
ReplayRunner = _module.ReplayRunner

def run_replay(evidence_path: str, allow_no_replay: bool = False):
    p = Path(evidence_path)
    if not p.exists():
        return {"status": "FAIL", "reason": "EVIDENCE_NOT_FOUND"}
    
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return {"status": "FAIL", "reason": f"PARSE_ERROR: {e}"}

    bundle = data.get("evidence_bundle", {}) if isinstance(data, dict) else {}
    if not isinstance(bundle, dict):
        return {"status": "FAIL", "reason": "INVALID_EVIDENCE_BUNDLE"}
    test_artifacts = bundle.get("test_artifacts", [])
    
    if not test_artifacts:
        if allow_no_replay:
            return {"status": "PARTIAL", "reason": "NO_TEST_ARTIFACTS_ALLOWED"}
        else:
            return {"status": "FAIL", "reason": "NO_TEST_ARTIFACTS_REJECTED"}
            
    # Statuses: PASS only when at least one allowlisted command was really replayed and
    # every replayed command matched; FAIL when a command was rejected/failed;
    # UNVERIFIED when nothing replayable was present (notes only) -- never a false PASS.
    report = ReplayRunner(REPO_ROOT).run_replay(bundle)
    summary = {
        "replay_count": report.get("replay_count", 0),
        "rejected_count": report.get("rejected_count", 0),
        "non_replayable_count": report.get("non_replayable_count", 0),
        "replay_results": report.get("replay_results", []),
    }
    # Nothing replayed (notes only): passed is False since #2685, but it is UNVERIFIED,
    # not a failed replay.
    if report.get("status") in {"SKIPPED", "NOT_REPLAYED"}:
        return {"status": "UNVERIFIED", "reason": "NO_REPLAYABLE_COMMANDS", **summary}
    if not report.get("passed"):
        return {"status": "FAIL", "reason": "REPLAY_" + str(report.get("status")), **summary}
    if summary["replay_count"] == 0:
        return {"status": "UNVERIFIED", "reason": "NO_REPLAYABLE_COMMANDS", **summary}
    return {"status": "PASS", **summary}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    parser.add_argument("--allow-no-replay", action="store_true", default=False)
    args = parser.parse_args()
    
    result = run_replay(args.evidence, args.allow_no_replay)
    print(json.dumps(result))
    # UNVERIFIED (nothing replayed) only exits 0 when the caller explicitly allows no replay.
    ok = result["status"] in ["PASS", "PARTIAL"] or (
        result["status"] == "UNVERIFIED" and args.allow_no_replay
    )
    sys.exit(0 if ok else 1)
