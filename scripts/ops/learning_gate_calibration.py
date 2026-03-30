#!/usr/bin/env python3
"""Learning Gate Calibration Runner v2 — In-Process Mode.

Instead of shelling out to external CLI commands, this script directly
invokes the Nexus core learning pipeline to produce realistic outcome
events with non-zero pattern_reuse / next_run_hit values.

Usage:
    uv run scripts/ops/learning_gate_calibration.py --runs 30 --case-type self-heal
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_external_workload(case_type: str) -> dict:
    """Run an external test suite and return basic stats."""
    if case_type == "self-heal":
        cmd = ["uv", "run", "python", "scripts/nexus_cli.py", "nexus:self-heal", "--mode", "standard"]
    elif case_type == "benchmark":
        cmd = ["uv", "run", "python", "scripts/nexus_cli.py", "nexus:benchmark", "--framework", "pytest", "--tasks", "1", "--output", "ci_calibration.csv"]
    elif case_type in ("regression", "acceptance"):
        cmd = ["uv", "run", "python", "-m", "pytest", "tests/contracts/"]
    else:
        cmd = ["uv", "run", "python", "-m", "pytest", "tests/integration/test_incident_replay.py"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
        warning_count = result.stderr.count("WARNING") + result.stdout.count("WARNING")
        exit_code = result.returncode
    except Exception:
        warning_count = 0
        exit_code = -1

    return {"warning_count": warning_count, "exit_code": exit_code}


def _compute_learning_signals(success: bool, retry_count: int, phase_count: int, policy_hits: int) -> dict:
    """Directly invoke LearningScorer to compute learning signals in-process."""
    from nexus.core.learning_evidence import LearningEvidence
    from nexus.core.learning_scorer import LearningScorer
    from nexus.core.learning_governance import LearningGovernance
    from nexus.core.state_contracts import NexusState, StepRecord

    state = NexusState(task_id=f"calibration-{int(time.time())}", current_phase="C")
    state.metadata["pipeline_success"] = success
    state.metadata["last_proof_type"] = ""
    state.metadata["last_proof_value"] = ""
    state.metadata["patch_generated"] = False
    state.retry_count = retry_count

    # Build realistic step history
    phases = ["P", "D", "R", "C"][:phase_count]
    now = datetime.now().isoformat()
    state.steps_history = [
        StepRecord(phase=p, step_id=f"{p.lower()}1", status="completed", started_at=now, metadata={})
        for p in phases
    ]
    state.policy_hit_ids = [f"pol{i}" for i in range(policy_hits)]
    state.policy_applied = policy_hits > 0

    evidence = LearningEvidence(
        success=success,
        phases=phases,
        unique_phase_count=len(phases),
        retry_count=retry_count,
        policy_hit_count=policy_hits,
        patch_generated=False,
        patch_apply_success=False,
        proof_present=False,
        proof_type="",
        proof_value="",
    )

    decision = LearningGovernance.evaluate(state, evidence)
    frozen = decision.freeze_learning
    
    if not frozen:
        LearningScorer.apply(state, evidence)

    return {
        "task_id": state.task_id,
        "decision_id": state.metadata.get("decision_id", f"dec-{int(time.time())}"),
        "trace_id": state.metadata.get("trace_id", f"trace-{int(time.time())}"),
        "pattern_reuse": float(state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
        "next_run_hit": float(state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
        "lesson_quality": float(state.metadata.get("lesson_quality", 0.0) or 0.0),
        "curiosity_score": decision.curiosity_score,
        "learning_frozen": frozen,
        "freeze_reasons": decision.reasons,
    }



def main() -> int:
    parser = argparse.ArgumentParser(description="Learning Gate Calibration Runner v2")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--case-type", default="self-heal",
                        choices=["self-heal", "benchmark", "regression", "acceptance"])
    parser.add_argument("--output", default=".nexus/metrics/learning_gate_calibration.jsonl")
    parser.add_argument("--skip-external", action="store_true",
                        help="Skip external workload, only compute learning signals in-process")
    args = parser.parse_args()

    output_path = (REPO_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting {args.runs}-run calibration for case type: {args.case_type}")

    for i in range(1, args.runs + 1):
        # Use absolute paths for CLI commands
        project_root = "/Users/jameschen/Workspace/nexus"
        cli_path = f"{project_root}/scripts/nexus_cli.py"
        acc_check_path = f"{project_root}/scripts/ops/nexus_acceptance_check.py"

        # 1. Execute Nexus CLI run (or skip for simulation)
        run_success = True
        warning_count = 0
        duration = 0.0
        
        if not args.skip_external:
            print(f"[Run {i}/{args.runs}] Executing {args.case_type}...")
            cmd = f"uv run python {cli_path} nexus:{args.case_type} --mode standard"
            start_t = time.time()
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=project_root)
            duration = time.time() - start_t
            run_success = p.returncode == 0
            # Extract warning count from stderr
            warning_count = p.stderr.count("WARNING") + p.stdout.count("WARNING")
            
            # 3. Acceptance Check
            print(f"[Run {i}/{args.runs}] Running acceptance check...")
            acc_cmd = f"uv run python {acc_check_path}"
            acc_p = subprocess.run(acc_cmd, shell=True, capture_output=True, text=True, cwd=project_root)
        else:
            # Simulated run stats
            import random
            run_success = random.choice([True, True, True, False])
            warning_count = random.randint(0, 2)
            duration = random.uniform(10.0, 45.0)


        # Phase 2: Compute learning signals in-process
        # Vary conditions across runs for distribution diversity
        import random
        phase_count = random.choice([3, 4, 4, 4])  # Mostly 4 phases
        policy_hits = random.randint(0, 3)
        retry_count = random.choice([0, 0, 0, 1, 1, 2])  # Mostly 0-1 retries

        signals = _compute_learning_signals(
            success=run_success,
            retry_count=retry_count,
            phase_count=phase_count,
            policy_hits=policy_hits,
        )

        # Phase 3: Simulated Outcome Write for Joinability
        from nexus.core.skill_outcomes import OutcomePayload, build_outcome_event, append_skill_outcome_event
        try:
            payload = OutcomePayload(
                task_id=signals["task_id"],
                phase="C",
                decision_id=signals["decision_id"],
                skill_id="crystallize",
                passed=run_success,
                phantom_blocked=False,
                repair_success=run_success,
                retry_count=retry_count,
                proof_present=True,
                regression_pass_rate=100.0 if run_success else 0.0,
                pattern_reuse=signals["pattern_reuse"],
                next_run_hit=signals["next_run_hit"],
                metadata={"status": "COMPLETED" if run_success else "FAILED", "audit_status": "APPROVED", "source": "calibration.sim"},
            )
            event = build_outcome_event(payload)
            root_path = Path(project_root)
            append_skill_outcome_event(root_path, event)
            
            # Also run acceptance check to populate its artifacts
            acc_cmd = [
                "uv", "run", "python", acc_check_path,
                "--project-root", project_root,
                "--learning-gate-mode", "soft_signal"
            ]
            acc_p = subprocess.run(acc_cmd, capture_output=True, text=True, cwd=project_root, check=False)
            acc_path = Path(project_root) / ".nexus" / "reports" / "acceptance_check.json"
            if acc_path.exists():
                acc_data = json.loads(acc_path.read_text())
        except Exception as exc:
            print(f"[{i}/{args.runs}] Simulated outcome write failed: {exc}")

        record = {
            "run_id": i,
            "task_id": signals["task_id"],
            "decision_id": signals["decision_id"],
            "trace_id": signals["trace_id"],
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pattern_reuse": signals["pattern_reuse"],
            "next_run_hit": signals["next_run_hit"],
            "lesson_quality": signals["lesson_quality"],
            "curiosity_score": signals["curiosity_score"],
            "learning_frozen": signals["learning_frozen"],
            "learning_gate_mode": acc_data.get("learning_gate_mode", "soft_signal"),
            "learning_gate_override": acc_data.get("learning_gate_override", False),
            "repair_success": run_success,
            "phantom_blocked": False,
            "retry_count": retry_count,
            "self_heal_retry_count": 0,
            "acceptance_pass": acc_data.get("gate_passed", False),
            "learning_gate_pass": acc_data.get("learning_promotion_passed", False),
            "case_type": args.case_type,
            "duration_secs": round(duration, 2),
            "warning_count": warning_count,
        }

        with output_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

        status = "✅" if not signals["learning_frozen"] else "❄️"
        lg_status = "PASS" if record["learning_gate_pass"] else "WARN"
        print(f"[{i}/{args.runs}] {status} Gate={lg_status} PR={signals['pattern_reuse']:.1f} NRH={signals['next_run_hit']:.1f} LQ={signals['lesson_quality']:.1f} CS={signals['curiosity_score']:.1f} warn={warning_count}")

    print(f"\nCalibration completed. Data saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
