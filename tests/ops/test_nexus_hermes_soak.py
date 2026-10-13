import argparse
import importlib.util
import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "ops" / "nexus-hermes-soak"
LOADER = SourceFileLoader("nexus_hermes_soak", str(PATH))
SPEC = importlib.util.spec_from_loader("nexus_hermes_soak", LOADER)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MOD)


def _args(tmp_path: Path, *, run_id: str = "soak-test", mode: str = "observe", cycles: int = 1):
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema":"nexus.hermes_controller_policy.v1","handlers":{}}\n')
    return argparse.Namespace(
        policy=str(policy),
        repo_root=str(tmp_path),
        repository="James3014/Nexus-new",
        issue=1395,
        pr=None,
        controller="/fake/controller",
        host_sync="/fake/host-sync",
        endpoint="http://127.0.0.1:8000/v1/models",
        state_dir=str(tmp_path / "state"),
        run_id=run_id,
        cycles=cycles,
        interval_seconds=0.0,
        mode=mode,
        allow_effect_canary=False,
        controller_max_cycles=3,
    )


def _healthy_host():
    return {
        "state": "ALIGNED",
        "installed_revision": "a" * 40,
        "installed_bundle_sha256": "b" * 64,
        "components": {
            "hermes_controller_guard": {
                "status": "VERIFIED",
                "sha256": "c" * 64,
            },
            "hermes_continuation_controller": {
                "status": "VERIFIED",
                "sha256": "d" * 64,
            },
        },
    }


def _safe_receipt(path: Path, run_id: str, *, disposition: str = "SAFE"):
    payload = {
        "schema": "nexus.hermes_controller_cycle_receipt.v1",
        "run_id": run_id,
        "cycle": 1,
        "doctor_disposition": disposition,
        "next_gate": "CONTINUE_BOUNDED_ISSUE_WORK",
        "receipt_hash": "e" * 64,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path, payload


def _stub_health(monkeypatch):
    monkeypatch.setattr(MOD, "_host_status", lambda host_sync: _healthy_host())
    monkeypatch.setattr(
        MOD,
        "_endpoint_health",
        lambda endpoint: {"status": "HEALTHY", "models": ["local-model"]},
    )
    monkeypatch.setattr(
        MOD,
        "_memory_health",
        lambda: {"status": "OBSERVED", "free_percentage": "42%"},
    )


def test_observe_cycle_passes_and_records_runtime_identity(tmp_path, monkeypatch):
    _stub_health(monkeypatch)

    def controller_run(**kwargs):
        return (
            {"outcome": "OBSERVED_ONLY", "run_id": kwargs["controller_run_id"]},
            subprocess.CompletedProcess(["controller"], 0, "", ""),
        )

    monkeypatch.setattr(MOD, "_controller_run", controller_run)
    monkeypatch.setattr(
        MOD,
        "_controller_cycle_receipt",
        lambda receipt_dir, controller_run_id: _safe_receipt(
            receipt_dir / controller_run_id / "cycle-0001.json",
            controller_run_id,
        ),
    )

    assert MOD.run_soak(_args(tmp_path)) == 0
    state = json.loads((tmp_path / "state/state.json").read_text())
    assert state["completed_cycles"] == 1
    assert state["next_cycle"] == 2
    assert state["in_progress_cycle"] is None
    cycle = json.loads((tmp_path / "state/cycles/cycle-00001.json").read_text())
    assert cycle["outcome"] == "PASS"
    assert cycle["host_runtime"]["state"] == "ALIGNED"
    assert cycle["local_model"]["status"] == "HEALTHY"
    assert cycle["doctor_disposition"] == "SAFE"


def test_wait_or_reconcile_receipt_fails_closed(tmp_path, monkeypatch):
    _stub_health(monkeypatch)
    monkeypatch.setattr(
        MOD,
        "_controller_run",
        lambda **kwargs: (
            {"outcome": "OBSERVED_ONLY"},
            subprocess.CompletedProcess(["controller"], 0, "", ""),
        ),
    )
    monkeypatch.setattr(
        MOD,
        "_controller_cycle_receipt",
        lambda receipt_dir, controller_run_id: _safe_receipt(
            receipt_dir / controller_run_id / "cycle-0001.json",
            controller_run_id,
            disposition="WAIT",
        ),
    )

    assert MOD.run_soak(_args(tmp_path)) == 3
    cycle = json.loads((tmp_path / "state/cycles/cycle-00001.json").read_text())
    assert cycle["outcome"] == "FAIL"
    assert "CONTROLLER_DOCTOR_NOT_SAFE:WAIT" in cycle["detail"]


def test_runtime_drift_blocks_before_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(
        MOD,
        "_host_status",
        lambda host_sync: (_ for _ in ()).throw(MOD.SoakError("HOST_RUNTIME_NOT_ALIGNED:STALE")),
    )
    monkeypatch.setattr(
        MOD,
        "_controller_run",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("controller must not run")),
    )

    assert MOD.run_soak(_args(tmp_path)) == 3
    state = json.loads((tmp_path / "state/state.json").read_text())
    assert state["failed"] is True
    assert state["in_progress_cycle"] == 1


def test_restart_retries_same_in_progress_cycle_and_clears_failure(tmp_path, monkeypatch):
    args = _args(tmp_path, run_id="resume-test")
    state_dir = tmp_path / "state"
    state = MOD._load_state(state_dir, "resume-test")
    state["in_progress_cycle"] = 3
    state["next_cycle"] = 3
    state["completed_cycles"] = 2
    state["failed"] = True
    state["failure_cycle"] = 3
    state["failure"] = "prior fault"
    MOD._save_state(state_dir, state)
    _stub_health(monkeypatch)

    seen = {}

    def controller_run(**kwargs):
        seen["run_id"] = kwargs["controller_run_id"]
        return (
            {"outcome": "OBSERVED_ONLY"},
            subprocess.CompletedProcess(["controller"], 0, "", ""),
        )

    monkeypatch.setattr(MOD, "_controller_run", controller_run)
    monkeypatch.setattr(
        MOD,
        "_controller_cycle_receipt",
        lambda receipt_dir, controller_run_id: _safe_receipt(
            receipt_dir / controller_run_id / "cycle-0001.json",
            controller_run_id,
        ),
    )

    assert MOD.run_soak(args) == 0
    assert seen["run_id"] == "resume-test-cycle-00003"
    final = json.loads((state_dir / "state.json").read_text())
    assert final["completed_cycles"] == 3
    assert final["next_cycle"] == 4
    assert final["failed"] is False
    assert "failure" not in final


def test_execute_requires_explicit_effect_authority(tmp_path):
    args = _args(tmp_path, mode="execute")
    try:
        MOD.run_soak(args)
    except MOD.SoakError as exc:
        assert str(exc) == "EXECUTE_MODE_REQUIRES_ALLOW_EFFECT_CANARY"
    else:
        raise AssertionError("execute mode must require explicit effect canary flag")


def test_execute_rejects_multi_cycle_effect_mode(tmp_path):
    args = _args(tmp_path, mode="execute", cycles=2)
    args.allow_effect_canary = True
    try:
        MOD.run_soak(args)
    except MOD.SoakError as exc:
        assert str(exc) == "EXECUTE_MODE_REQUIRES_SINGLE_CYCLE"
    else:
        raise AssertionError("execute mode must remain single-cycle bounded")


def test_endpoint_failure_blocks_before_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "_host_status", lambda host_sync: _healthy_host())
    monkeypatch.setattr(
        MOD,
        "_endpoint_health",
        lambda endpoint: (_ for _ in ()).throw(MOD.SoakError("LOCAL_MODEL_ENDPOINT_UNAVAILABLE")),
    )
    monkeypatch.setattr(
        MOD,
        "_controller_run",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("controller must not run")),
    )

    assert MOD.run_soak(_args(tmp_path)) == 3


def test_host_status_resolves_current_main_bundle_before_verify(tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "desired":
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps({
                    "state": "DESIRED_RESOLVED",
                    "desired_revision": "a" * 40,
                    "desired_bundle_sha256": "b" * 64,
                }),
                "",
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(_healthy_host()),
            "",
        )

    monkeypatch.setattr(MOD, "_run", fake_run)
    payload = MOD._host_status("/fake/host-sync")
    assert payload["state"] == "ALIGNED"
    assert calls[0] == ["/fake/host-sync", "desired", "--track-ref", "main"]
    assert calls[1] == [
        "/fake/host-sync",
        "verify",
        "--desired-bundle-sha256",
        "b" * 64,
    ]
