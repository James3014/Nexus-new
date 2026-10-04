from __future__ import annotations

import fcntl
import importlib.util
import json
import plistlib
import subprocess
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "ops" / "nexus-hermes-launchd"
LOADER = SourceFileLoader("nexus_hermes_launchd", str(PATH))
SPEC = importlib.util.spec_from_loader("nexus_hermes_launchd", LOADER)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MOD)


class FakeLaunchctl:
    def __init__(self) -> None:
        self.loaded: set[str] = set()
        self.disabled: dict[str, bool] = {}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(tuple(args))
        verb = args[0]
        if verb == "print":
            label = args[1].split("/")[-1]
            if label not in self.loaded:
                return subprocess.CompletedProcess(
                    ["launchctl", *args],
                    3,
                    "",
                    "Could not find service",
                )
            return subprocess.CompletedProcess(
                ["launchctl", *args],
                0,
                "state = running\npid = 123\nlast exit code = 0\n",
                "",
            )
        if verb == "print-disabled":
            body = "disabled services = {\n"
            for label, disabled in sorted(self.disabled.items()):
                body += f'    "{label}" => {"true" if disabled else "false"}\n'
            body += "}\n"
            return subprocess.CompletedProcess(["launchctl", *args], 0, body, "")
        if verb in {"disable", "enable"}:
            label = args[1].split("/")[-1]
            self.disabled[label] = verb == "disable"
            return subprocess.CompletedProcess(["launchctl", *args], 0, "", "")
        if verb == "bootout":
            label = args[1].split("/")[-1]
            self.loaded.discard(label)
            return subprocess.CompletedProcess(["launchctl", *args], 0, "", "")
        if verb == "bootstrap":
            plist = Path(args[2])
            with plist.open("rb") as handle:
                label = plistlib.load(handle)["Label"]
            self.loaded.add(label)
            return subprocess.CompletedProcess(["launchctl", *args], 0, "", "")
        raise AssertionError(args)


def _config(tmp_path: Path, monkeypatch, *, target_mode: str = "observe"):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    state_root = home / ".local/state/nexus-hermes-service"
    target = state_root / "target.json"
    evidence = state_root / "activation-evidence.json"
    model_binary = tmp_path / "splash"
    model_binary.write_bytes(b"splash-binary")
    model_binary.chmod(0o755)
    controller = tmp_path / "nexus-hermes-continuation-controller"
    guard = tmp_path / "nexus-hermes-controller-guard"
    doctor = tmp_path / "nexus-workflow-doctor"
    host_sync = tmp_path / "nexus-host-sync"
    for path in (controller, guard, doctor, host_sync):
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema": "nexus.hermes_controller_policy.v1", "handlers": {}}))
    config = {
        "schema": MOD.CONFIG_SCHEMA,
        "state_root": str(state_root),
        "target_path": str(target),
        "activation_evidence_path": str(evidence),
        "controller_path": str(controller),
        "guard_path": str(guard),
        "doctor_path": str(doctor),
        "host_sync_path": str(host_sync),
        "model_endpoint": "http://127.0.0.1:8000/v1/models",
        "model_binary": str(model_binary),
        "model_binary_sha256": MOD._sha256_file(model_binary),
        "model_id": "incoai/Qwen3.6-35B-A3B-Splash",
        "model_context": 65536,
        "model_port": 8000,
        "start_interval_seconds": 120,
    }
    config_path = state_root / "service.json"
    MOD._atomic_json(config_path, config)
    target_payload = {
        "schema": MOD.TARGET_SCHEMA,
        "enabled": True,
        "repository": "James3014/Nexus-new",
        "repo_root": str(repo_root),
        "issue": 1397,
        "policy_path": str(policy),
        "policy_sha256": MOD._sha256_file(policy),
        "mode": target_mode,
        "max_cycles": 3,
    }
    MOD._atomic_json(target, target_payload)
    monkeypatch.setenv("NEXUS_HERMES_LAUNCHD_TARGET", str(tmp_path / "nexus-hermes-launchd"))
    return config_path, config, target_payload


def test_plists_bind_exact_model_and_contain_no_secrets(tmp_path, monkeypatch):
    config_path, config, _ = _config(tmp_path, monkeypatch)
    controller, model = MOD._plist_payloads(config_path, config)
    assert controller["Label"] == MOD.DEFAULT_CONTROLLER_LABEL
    assert controller["ProgramArguments"][1:] == ["tick", "--config", str(config_path)]
    assert controller["StartInterval"] == 120
    assert model["Label"] == MOD.DEFAULT_MODEL_LABEL
    assert model["ProgramArguments"][0] == str(Path(config["model_binary"]).resolve())
    assert "--max-context" in model["ProgramArguments"]
    assert "65536" in model["ProgramArguments"]
    serialized = json.dumps({"controller": controller, "model": model}).lower()
    assert "token" not in serialized
    assert "oauth" not in serialized
    assert "api_key" not in serialized


def test_stage_writes_plists_disables_and_never_bootstraps(tmp_path, monkeypatch):
    config_path, config, _ = _config(tmp_path, monkeypatch)
    runner = FakeLaunchctl()
    result = MOD._stage(config_path, config, runner=runner)
    assert result["status"] == "STAGED_DISABLED"
    controller_plist, model_plist = MOD._plist_paths(config)
    assert controller_plist.is_file()
    assert model_plist.is_file()
    assert runner.disabled[MOD.DEFAULT_CONTROLLER_LABEL] is True
    assert runner.disabled[MOD.DEFAULT_MODEL_LABEL] is True
    assert not any(call[0] == "bootstrap" for call in runner.calls)


def test_activate_requires_elapsed_soak_before_launchctl_effect(tmp_path, monkeypatch):
    config_path, config, _ = _config(tmp_path, monkeypatch)
    runner = FakeLaunchctl()
    MOD._write_plists(config_path, config)
    with pytest.raises(MOD.HermesLaunchdError, match="activation-evidence"):
        MOD._activate(config_path, config, runner=runner)
    assert runner.calls == []


def test_activate_rejects_unmanaged_live_model_endpoint(tmp_path, monkeypatch):
    config_path, config, _ = _config(tmp_path, monkeypatch)
    runner = FakeLaunchctl()
    MOD._write_plists(config_path, config)
    monkeypatch.setattr(
        MOD,
        "_activation_evidence",
        lambda _config: {"schema": MOD.ACTIVATION_SCHEMA, "status": "PASS"},
    )
    monkeypatch.setattr(
        MOD,
        "_endpoint_health",
        lambda _config, timeout=3.0: {"status": "HEALTHY", "models": [config["model_id"]]},
    )
    with pytest.raises(MOD.HermesLaunchdError, match="MODEL_ENDPOINT_ALREADY_LIVE_OUTSIDE_LAUNCHD"):
        MOD._activate(config_path, config, runner=runner)
    assert not any(call[0] == "bootstrap" for call in runner.calls)


def _write_soak(
    root: Path,
    *,
    runtime_revision: str,
    runtime_bundle: str,
    hours: float,
) -> None:
    run_id = "elapsed-soak"
    cycles = root / "cycles"
    receipts = root / "controller-receipts"
    cycles.mkdir(parents=True)
    receipts.mkdir(parents=True)
    start = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    finish = start + timedelta(hours=hours)
    state = {
        "schema": "nexus.hermes_soak_state.v1",
        "claim_ceiling": "SOAK_QUALIFICATION_ONLY_NO_ACCEPTANCE_MERGE_RELEASE",
        "run_id": run_id,
        "next_cycle": 3,
        "in_progress_cycle": None,
        "completed_cycles": 2,
        "failed": False,
    }
    MOD._atomic_json(root / "state.json", state)
    for index, when in ((1, start), (2, finish)):
        cycle = {
            "schema": "nexus.hermes_soak_cycle.v1",
            "claim_ceiling": "SOAK_QUALIFICATION_ONLY_NO_ACCEPTANCE_MERGE_RELEASE",
            "run_id": run_id,
            "cycle": index,
            "controller_run_id": f"{run_id}-cycle-{index:05d}",
            "mode": "observe",
            "started_at": when.isoformat(),
            "finished_at": when.isoformat(),
            "outcome": "PASS",
            "host_runtime": {
                "installed_revision": runtime_revision,
                "installed_bundle_sha256": runtime_bundle,
            },
            "local_model": {"status": "HEALTHY"},
            "doctor_disposition": "SAFE",
        }
        MOD._atomic_json(cycles / f"cycle-{index:05d}.json", cycle)
        controller_dir = receipts / cycle["controller_run_id"]
        controller_dir.mkdir()
        MOD._atomic_json(
            controller_dir / "state.json",
            {
                "schema": "nexus.hermes_controller_state.v1",
                "run_id": cycle["controller_run_id"],
                "effects_started": 0,
            },
        )


def test_accept_soak_rejects_less_than_six_hours(tmp_path, monkeypatch):
    _, config, _ = _config(tmp_path, monkeypatch)
    soak = tmp_path / "soak"
    _write_soak(soak, runtime_revision="a" * 40, runtime_bundle="b" * 64, hours=5.9)
    monkeypatch.setattr(
        MOD,
        "_host_runtime",
        lambda _config: {
            "installed_revision": "a" * 40,
            "installed_bundle_sha256": "b" * 64,
        },
    )
    with pytest.raises(MOD.HermesLaunchdError, match="SOAK_ELAPSED_TOO_SHORT"):
        MOD._accept_soak(config, soak, tmp_path / "evidence.json", 6.0)


def test_accept_soak_writes_exact_runtime_evidence_after_six_hours(tmp_path, monkeypatch):
    _, config, _ = _config(tmp_path, monkeypatch)
    soak = tmp_path / "soak"
    output = tmp_path / "evidence.json"
    _write_soak(soak, runtime_revision="a" * 40, runtime_bundle="b" * 64, hours=6.1)
    monkeypatch.setattr(
        MOD,
        "_host_runtime",
        lambda _config: {
            "installed_revision": "a" * 40,
            "installed_bundle_sha256": "b" * 64,
        },
    )
    evidence = MOD._accept_soak(config, soak, output, 6.0)
    assert evidence["schema"] == MOD.ACTIVATION_SCHEMA
    assert evidence["status"] == "PASS"
    assert evidence["elapsed_seconds"] >= MOD.MIN_SOAK_SECONDS
    assert evidence["runtime_revision"] == "a" * 40
    assert evidence["runtime_bundle_sha256"] == "b" * 64
    assert output.is_file()


def test_activation_rejects_tampered_indexed_soak_receipt(tmp_path, monkeypatch):
    _, config, _ = _config(tmp_path, monkeypatch)
    soak = tmp_path / "soak"
    output = Path(config["activation_evidence_path"])
    _write_soak(soak, runtime_revision="a" * 40, runtime_bundle="b" * 64, hours=6.1)
    monkeypatch.setattr(
        MOD,
        "_host_runtime",
        lambda _config: {
            "installed_revision": "a" * 40,
            "installed_bundle_sha256": "b" * 64,
        },
    )
    MOD._accept_soak(config, soak, output, 6.0)
    cycle = soak / "cycles" / "cycle-00002.json"
    cycle.write_text(cycle.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(MOD.HermesLaunchdError, match="ACTIVATION_RECEIPT_HASH_MISMATCH"):
        MOD._activation_evidence(config)


def test_second_tick_is_noop_while_service_lock_is_held(tmp_path, monkeypatch):
    config_path, config, _ = _config(tmp_path, monkeypatch)
    state_root = Path(config["state_root"])
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / "tick.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = MOD._tick(config_path, config, allow_staged=True)
        assert result["status"] == "NOOP_TICK_ALREADY_RUNNING"
        assert result["lock_path"] == str(lock_path)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def test_staged_tick_reuses_stable_observe_controller_identity(tmp_path, monkeypatch):
    _, config, _ = _config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        MOD,
        "_host_runtime",
        lambda _config: {
            "state": "ALIGNED",
            "installed_revision": "a" * 40,
            "installed_bundle_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        MOD,
        "_endpoint_health",
        lambda _config, timeout=3.0: {"status": "HEALTHY", "models": [config["model_id"]]},
    )
    monkeypatch.setattr(
        MOD,
        "_controller_state",
        lambda _config, _run_id: {
            "schema": "nexus.hermes_controller_state.v1",
            "effects_started": 0,
            "operation_id": None,
            "effect_intent": None,
        },
    )
    monkeypatch.setattr(
        MOD,
        "_doctor",
        lambda _config, _target, _operation_id: {
            "schema": "nexus.workflow_doctor.v1",
            "claim_ceiling": "READ_ONLY_WORKFLOW_OBSERVATION",
            "resume_disposition": "SAFE",
            "next_gate": {"code": "CONTINUE_BOUNDED_ISSUE_WORK"},
            "operation": {"active": []},
            "leases": {"active": []},
        },
    )

    calls: list[str] = []

    def fake_run(argv, *, cwd=None, timeout=60, env=None):
        run_id = argv[argv.index("--run-id") + 1]
        calls.append(run_id)
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"outcome": "OBSERVED_ONLY"}) + "\n", ""
        )

    monkeypatch.setattr(MOD, "_run", fake_run)
    first = MOD._tick(tmp_path / "service.json", config, allow_staged=True)
    second = MOD._tick(tmp_path / "service.json", config, allow_staged=True)
    assert first["controller_run_id"] == second["controller_run_id"]
    assert calls == [first["controller_run_id"], first["controller_run_id"]]
    state = MOD._load_state(config)
    assert state["epoch"] == 1
    assert state["epoch_status"] == "ACTIVE"
