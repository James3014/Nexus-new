#!/usr/bin/env python3
import json
import sys
import subprocess
from pathlib import Path

# Ensure nexus package is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nexus.core.hallucination_guard import HallucinationGuard

def verify_evidence(evidence_path: str, allow_no_replay: bool = False):
    """Verify an evidence file.

    VERIFIED requires a real passing replay (replay status PASS: at least one allowlisted
    command was actually re-executed and matched). Notes-only evidence (replay UNVERIFIED /
    NO_REPLAYABLE_COMMANDS) is returned as UNVERIFIED with a non-zero CLI exit.
    ``allow_no_replay`` (CLI: --allow-no-replay) is the explicit waiver: the verdict may then
    be VERIFIED, but it is labelled ``replay_waived: true`` / ``replay_verified: false`` and
    trust is capped at MEDIUM.
    """
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

    replay_verified = replay_data.get("status") == "PASS"
    # A replay that ran no tests (only `pytest --version` / `--collect-only` / `ruff check`)
    # proves nothing about tests passing: never VERIFIED/HIGH on that alone (#2685).
    runs_no_tests = replay_verified and not replay_data.get("test_running_count", 0)
    if runs_no_tests:
        replay_verified = False
    replay_waived = False
    reason = None
    if status == "VERIFIED" and not replay_verified:
        if allow_no_replay:
            replay_waived = True
        else:
            # Notes-only evidence (nothing replayed) must never be VERIFIED.
            status = "UNVERIFIED"
            if runs_no_tests:
                reason = "NO_TEST_RUNNING_COMMAND"
            elif replay_data.get("status") == "UNVERIFIED":
                reason = "NO_REPLAYABLE_COMMANDS"
            else:
                reason = "REPLAY_NOT_PASSED"

    if status == "VERIFIED":
        trust = "MEDIUM" if replay_waived else "HIGH"
    else:
        trust = "LOW"
    result = {
        "status": status,
        "overall_trust": trust,
        "replay": replay_data,
        # Replay status UNVERIFIED means nothing replayable was present; surface it explicitly.
        "replay_verified": replay_verified,
        "replay_waived": replay_waived,
        "hallucination_index": analysis
    }
    if reason:
        result["reason"] = reason
        result["message"] = (
            "No allowlisted test command was replayed; evidence is not verified. "
            "Provide a replayable test_artifacts command or pass --allow-no-replay explicitly."
        )
        if reason == "NO_TEST_RUNNING_COMMAND":
            result["message"] = (
                "The replayed commands run no tests (e.g. pytest --version / --collect-only); "
                "evidence is not verified. Provide a command that runs the tests."
            )
    if replay_waived:
        result["message"] = "Replay explicitly waived via --allow-no-replay; evidence was NOT replay-verified."
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    parser.add_argument(
        "--allow-no-replay",
        action="store_true",
        default=False,
        help="Explicitly waive the replay requirement: notes-only evidence may then be VERIFIED "
        "but is labelled replay_waived=true and capped at MEDIUM trust.",
    )
    args = parser.parse_args()
    
    result = verify_evidence(args.evidence, args.allow_no_replay)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "VERIFIED" else 1)
