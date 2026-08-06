import json
from pathlib import Path

import pytest


def _write_runtime_receipt(receipt_path, receipt):
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")


def test_build_command_service_constructs_engine_once(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_command_service

    captured = {}

    class _FakeEngineConfig:
        def __init__(self, project_root):
            captured["config_project_root"] = project_root

    class _FakeEngine:
        def __init__(self, config):
            captured["engine_config"] = config

    class _FakeService:
        def __init__(self, engine):
            captured["service_engine"] = engine

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _FakeEngineConfig)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", _FakeEngine)
    monkeypatch.setattr("nexus.app.command_service.NexusCommandService", _FakeService)

    service = build_command_service(tmp_path)

    assert isinstance(service, _FakeService)
    assert captured["config_project_root"] == tmp_path
    assert captured["service_engine"] is not None


def test_build_engine_passes_config_overrides(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_engine

    captured = {}

    class _FakeEngineConfig:
        def __init__(self, project_root, **kwargs):
            captured["project_root"] = project_root
            captured["kwargs"] = kwargs

    class _FakeEngine:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _FakeEngineConfig)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", _FakeEngine)

    engine = build_engine(tmp_path, benchmark_mode=True, silent=True)

    assert isinstance(engine, _FakeEngine)
    assert captured["project_root"] == tmp_path
    assert captured["kwargs"] == {"benchmark_mode": True, "silent": True}


def test_execute_single_task_via_service_uses_build_command_service(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import execute_single_task_via_service

    called = {}

    class _FakeService:
        def execute_bug(self, request):
            called["kind"] = "bug"
            called["task"] = request.task
            return True

        def execute_feature(self, request):
            called["kind"] = "feature"
            called["task"] = request.task
            return True

    def _fake_build_command_service(project_root):
        called["project_root"] = project_root
        return _FakeService()

    monkeypatch.setattr("nexus.engine.canonical_task_seam.build_command_service", _fake_build_command_service)

    ok = execute_single_task_via_service("fix race", tmp_path)

    assert ok is True
    assert called["project_root"] == tmp_path
    assert called["kind"] == "bug"
    assert called["task"] == "fix race"


def test_build_legacy_cli_service_shapes_bug_request(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_legacy_cli_service

    captured = {}

    class _FakeCommandService:
        def execute_bug(self, request):
            captured["request"] = request
            return True

        def execute_feature(self, request):
            raise AssertionError("feature path should not be used")

    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda project_root: _FakeCommandService(),
    )

    service = build_legacy_cli_service(tmp_path)
    ok = service.execute_bug(
        "fix bug",
        delivery_mode="high",
        bug_id="BUG-1",
        verify_commands=["pytest -q"],
        artifact_paths=["report.json"],
        plan_only=True,
    )

    assert ok is True
    request = captured["request"]
    assert request.task == "fix bug"
    assert request.task_id == "BUG-1"
    assert request.delivery_mode == "high"
    assert request.verify_commands == ["pytest -q"]
    assert request.artifact_paths == ["report.json"]
    assert request.plan_only is True


def test_build_legacy_cli_service_shapes_feature_request(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_legacy_cli_service

    captured = {}

    class _FakeCommandService:
        def execute_bug(self, request):
            raise AssertionError("bug path should not be used")

        def execute_feature(self, request):
            captured["request"] = request
            return True

    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda project_root: _FakeCommandService(),
    )

    service = build_legacy_cli_service(tmp_path)
    ok = service.execute_feature(
        "build dashboard",
        domain="frontend",
        delivery_mode="standard",
        verify_commands=["pytest -q tests/ui"],
    )

    assert ok is True
    request = captured["request"]
    assert request.task == "build dashboard"
    assert request.domain == "frontend"
    assert request.delivery_mode == "standard"
    assert request.verify_commands == ["pytest -q tests/ui"]


def test_canonical_product_task_enters_gateway_once_without_legacy_fallback(
    monkeypatch,
    tmp_path,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    captured = {"calls": 0}

    class _Gateway:
        def __init__(self, project_root):
            captured["project_root"] = project_root

        def ask_unified(self, request, **kwargs):
            captured["calls"] += 1
            captured["request"] = request
            captured["kwargs"] = kwargs
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {
                    "execution_decision_authority": "CapabilityPlanner",
                },
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            _write_runtime_receipt(kwargs["receipt_path"], receipt)
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )
    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy command service must not be constructed")
        ),
    )

    result = execute_canonical_product_task(
        "audit bounded runtime",
        tmp_path,
        execution_context={
            "task_id": "canonical-product-1",
            "workspace_revision": "rev-1",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )

    assert bool(result) is True
    assert captured["calls"] == 1
    request = captured["request"]
    assert request.canonical_planning_bundle is not None
    assert request.route["online_policy"] == "auto"
    assert set(request.route).isdisjoint(
        {"provider", "model", "execution_topology", "recommended_flow"}
    )
    assert request.route["workforce_bindings"]["online"]["worker_id"] == "grok_review"
    assert "provider" not in request.route["workforce_bindings"]["online"]
    assert result.production_ingress_count == 1
    assert result.production_runtime_entry_count == 1


def test_canonical_product_verified_repair_topology_is_planner_owned(
    monkeypatch,
    tmp_path,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    (tmp_path / "target.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    captured = {}

    class _Gateway:
        def __init__(self, project_root):
            pass

        def ask_unified(self, request, **kwargs):
            captured["request"] = request
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {
                    "execution_decision_authority": "CapabilityPlanner",
                },
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            _write_runtime_receipt(kwargs["receipt_path"], receipt)
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )

    result = execute_canonical_product_task(
        "repair target.py and independently review the verified result",
        tmp_path,
        execution_context={
            "task_id": "canonical-world-c-1",
            "workspace_revision": "rev-world-c",
            "local_assist_mode": "advisor",
            "online_policy": "auto",
            "target_files": ["target.py"],
            "target_file": "target.py",
            "verifier_command": ["python", "-m", "py_compile", "target.py"],
        },
    )

    request = captured["request"]
    assert bool(result) is True
    assert request.local_request.action == "verified-subtask"
    assert request.local_request.planner_snapshot["execution_topology"] == "ISOLATED_TARGET"
    assert request.local_request.planner_snapshot["executor_topology"] == "localheal_pipeline"
    assert request.local_request.planner_snapshot["executor_provider"] == "workforce_admission"
    assert request.local_request.planner_snapshot["executor_model"] == "workforce_admission"
    assert request.route["workforce_bindings"]["local"]["worker_id"] == "local_coder_7b"
    assert request.codeintel["workspace_root"] == str(tmp_path.resolve())
    assert request.codeintel["verify_commands"] == [
        "python -m py_compile target.py"
    ]
    assert request.codeintel["mempalace_tenant_id"] == "canonical-product"
    assert request.codeintel["mempalace_artifact"]["task_id"] == "canonical-world-c-1"
    assert request.route["workforce_bindings"]["online"]["worker_id"] == "grok_review"


def test_canonical_product_online_deny_removes_online_runtime_demand(
    monkeypatch,
    tmp_path,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    (tmp_path / "target.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    captured = {}

    class _Gateway:
        def __init__(self, project_root):
            pass

        def ask_unified(self, request, **kwargs):
            captured["request"] = request
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {
                    "execution_decision_authority": "CapabilityPlanner",
                },
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            _write_runtime_receipt(kwargs["receipt_path"], receipt)
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )

    execute_canonical_product_task(
        "repair target.py with the local verified pipeline",
        tmp_path,
        execution_context={
            "task_id": "canonical-world-c-local-only",
            "workspace_revision": "rev-world-c-local-only",
            "local_assist_mode": "advisor",
            "online_policy": "deny",
            "target_files": ["target.py"],
            "target_file": "target.py",
            "verifier_command": ["python", "-m", "py_compile", "target.py"],
        },
    )

    request = captured["request"]
    assert request.online_enabled is False
    assert request.local_enabled is True
    assert request.canonical_planning_bundle.context.execution_channels == ("local",)
    assert set(request.route["workforce_bindings"]) == {"local"}


def test_canonical_product_rejects_caller_route_override(tmp_path):
    import pytest

    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    with pytest.raises(
        ValueError,
        match="canonical_product_caller_override_forbidden:provider",
    ):
        execute_canonical_product_task(
            "audit runtime",
            tmp_path,
            execution_context={
                "task_id": "override-1",
                "workspace_revision": "rev-1",
                "local_assist_mode": "disabled",
                "online_policy": "auto",
                "provider": "gemini",
            },
        )


def test_canonical_product_fails_closed_when_disk_receipt_differs(
    monkeypatch,
    tmp_path,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    class _TamperingGateway:
        def __init__(self, project_root):
            pass

        def ask_unified(self, request, **kwargs):
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {
                    "execution_decision_authority": "CapabilityPlanner",
                },
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            tampered = {**receipt, "terminal_status": "BLOCKED"}
            _write_runtime_receipt(kwargs["receipt_path"], tampered)
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _TamperingGateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )

    result = execute_canonical_product_task(
        "audit bounded runtime",
        tmp_path,
        execution_context={
            "task_id": "disk-tamper-1",
            "workspace_revision": "rev-1",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )

    assert bool(result) is False
    assert result.root_receipt_valid is False
    assert "runtime_receipt_disk_mismatch" in result.root_receipt_blockers


@pytest.mark.parametrize("unsafe_target", ("../outside.py", "/tmp/outside.py", "bad\\path.py"))
def test_canonical_product_rejects_unsafe_target_before_runtime(
    tmp_path,
    unsafe_target,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    with pytest.raises(ValueError, match="canonical_product_target_path_invalid"):
        execute_canonical_product_task(
            "repair one bounded target",
            tmp_path,
            execution_context={
                "task_id": "unsafe-target-1",
                "workspace_revision": "rev-1",
                "local_assist_mode": "advisor",
                "online_policy": "auto",
                "target_files": [unsafe_target],
                "target_file": unsafe_target,
                "verifier_command": ["python", "-m", "py_compile", unsafe_target],
            },
        )


def test_canonical_product_rejects_target_symlink_outside_workspace(tmp_path):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")
    (tmp_path / "target.py").symlink_to(outside)

    with pytest.raises(ValueError, match="canonical_product_target_path_invalid"):
        execute_canonical_product_task(
            "repair one bounded target",
            tmp_path,
            execution_context={
                "task_id": "unsafe-symlink-1",
                "workspace_revision": "rev-1",
                "local_assist_mode": "advisor",
                "online_policy": "auto",
                "target_files": ["target.py"],
                "target_file": "target.py",
                "verifier_command": ["python", "-m", "py_compile", "target.py"],
            },
        )
