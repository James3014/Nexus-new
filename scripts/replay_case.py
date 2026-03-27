#!/usr/bin/env python3
import sys
import json
import argparse
import time
from pathlib import Path

# Ensure project imports work
sys.path.append(str(Path.cwd()))


def execute_replay_case(
    cli,
    *,
    case_type: str,
    case_id: str,
    goal: str,
    delivery_mode: str = "standard",
    verify_commands: list[str] | None = None,
    artifact_paths: list[str] | None = None,
) -> bool:
    if case_type == "bug":
        return cli.service.execute_bug(
            goal,
            delivery_mode=delivery_mode,
            verify_commands=verify_commands,
            artifact_paths=artifact_paths,
            bug_id=case_id,
        )
    return cli.service.execute_feature(
        goal,
        delivery_mode=delivery_mode,
        verify_commands=verify_commands,
        artifact_paths=artifact_paths,
    )


def replay_case(
    case_id: str,
    delivery_mode: str = "standard",
    verify_commands: list[str] | None = None,
    artifact_paths: list[str] | None = None,
):
    project_root = Path.cwd()
    catalog_path = project_root / "cases" / "catalog.json"

    if not catalog_path.exists():
        print(f"❌ Catalog not found at {catalog_path}")
        return

    catalog = json.loads(catalog_path.read_text())
    case_meta = next((c for c in catalog["cases"] if c["id"] == case_id), None)

    if not case_meta:
        print(f"❌ Case {case_id} not found in catalog.")
        return

    case_file = project_root / "cases" / case_meta["file"]
    if not case_file.exists():
        print(f"❌ Case file {case_file} missing.")
        return

    case_data = json.loads(case_file.read_text())
    print(f"🎬 [Replay] Starting Case: {case_id} ({case_data['goal']})")

    # Setup isolated run directory
    run_dir = project_root / ".nexus" / "replays" / case_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Standard DI Setup (v1.8 Core)
    from nexus.app.command_service import NexusCommandService
    from nexus.containers import NexusContainer
    from nexus.delivery.interactive import resolve_delivery_mode
    from scripts.engine.nexus_cli import NexusCLI

    container = NexusContainer()
    container.project_root.from_value(str(project_root))

    # Initialize Engine via Container
    engine = container.engine_factory(
        project_root=project_root, run_dir=run_dir, silent=True
    )

    # Override state_io to use replay location
    state_file = run_dir / "replay_state.jsonl"
    state_io = container.state_io(state_file=str(state_file))
    engine.state_io = state_io
    cli = NexusCLI(project_root=project_root, output_dir=run_dir, silent=True)
    cli._engine = engine
    cli._service = NexusCommandService(engine)
    resolved_delivery_mode = resolve_delivery_mode(delivery_mode)

    start_time = time.time()
    success = False

    try:
        success = execute_replay_case(
            cli,
            case_type=case_meta["type"],
            case_id=case_id,
            goal=case_data["goal"],
            delivery_mode=resolved_delivery_mode,
            verify_commands=verify_commands,
            artifact_paths=artifact_paths,
        )
    except Exception as e:
        print(f"💥 [Replay] Execution Failed: {e}")

    duration = time.time() - start_time

    # Validation
    expected = case_data.get("expected_outcome", {})
    final_state = state_io.load_global_state()
    history_phases = [h.phase for h in final_state.steps_history]

    print(f"\n📊 [Replay Results: {case_id}]")
    print(f"⏱️  Duration: {duration:.2f}s")
    print(f"✅ Success: {success}")
    print(f"🛣️  Phases Reached: {' -> '.join(history_phases)}")

    # CHK-003: Drift Detection
    baseline = case_data.get("metadata", {}).get("baseline")
    drift_index = 0.0
    if baseline:
        print("\n⚖️ [Drift Analysis]")
        # 1. Token Drift
        base_tokens = baseline.get("tokens", 1)
        curr_tokens = final_state.total_token_usage
        token_drift = abs(curr_tokens - base_tokens) / base_tokens
        print(f"  - Token Drift: {token_drift:.2%} ({curr_tokens} vs {base_tokens})")

        # 2. Path Drift
        base_phases = baseline.get("phases", [])
        curr_phases = history_phases
        phase_drift = 0.0 if curr_phases == base_phases else 0.5
        if phase_drift > 0:
            print(
                f"  - Path Drift Detected! Expected: {base_phases}, Got: {curr_phases}"
            )

        drift_index = (token_drift * 0.5) + phase_drift
        print(f"  - Final Drift Index: {drift_index:.4f}")

        # Sync to health metrics
        final_state.health_metrics.drift_index = drift_index
        final_state.calculate_health()
        state_io.save_global_state(final_state)
        print(
            f"🏥 [Health] New Score: {final_state.health_score} ({final_state.health_metrics.status})"
        )

    # [IMP-103] Hard Gate Mechanism
    gate_failed = False
    missing_phases = [p for p in expected.get("phases", []) if p not in history_phases]
    if missing_phases:
        print(f"\n❌ [GATE-FAIL] Missing phases: {missing_phases}")
        gate_failed = True

    drift_threshold = catalog.get("config", {}).get(
        "default_token_drift_threshold", 0.2
    )
    if drift_index > drift_threshold:
        print(
            f"\n❌ [GATE-FAIL] Drift index {drift_index:.4f} exceeds threshold {drift_threshold}"
        )
        gate_failed = True

    if gate_failed:
        print("\n🛑 [Nexus:Gate] Validation failed. Exiting with error.")
        sys.exit(1)
    else:
        print("\n✨ [Nexus:Gate] Validation passed.")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexus Offline Case Replayer")
    parser.add_argument("case_id", help="ID of the case to replay (e.g., OFF-001)")
    parser.add_argument(
        "--delivery-mode",
        choices=["ask", "standard", "high"],
        default="standard",
        help="Prompt or choose whether replay must satisfy high-standard delivery verification.",
    )
    parser.add_argument("--verify", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    args = parser.parse_args()

    replay_case(
        args.case_id,
        delivery_mode=args.delivery_mode,
        verify_commands=args.verify,
        artifact_paths=args.artifact,
    )
