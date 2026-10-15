import json
from pathlib import Path

import pytest


def _write_runtime_receipt(receipt_path, receipt):
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")


@pytest.mark.parametrize(
    ("task_text", "expected"),
    (
        ("repair add_one so the verifier passes", "bug"),
        ("fix address parsing in the repair target", "bug"),
        ("repair additional validation", "bug"),
        ("fix rebuild_index regression", "bug"),
        ("repair create_cache regression", "bug"),
        ("repair éadd parser", "bug"),
        ("repair addé parser", "bug"),
        ("修理add錯誤", "bug"),
        ("add a dashboard feature", "feature"),
        ("Create a dashboard", "feature"),
        ("Implement the export feature", "feature"),
        ("build a new report", "feature"),
    ),
)
def test_infer_task_kind_uses_identifier_safe_feature_intent(task_text, expected):
    from nexus.engine.canonical_task_seam import infer_task_kind

    assert infer_task_kind(task_text) == expected


# ARCHIVED 2026-10-13 legacy-engine (ARCHIVED_2026-10-13-legacy-engine.md): the legacy
# NexusEngine / CommandService builders fail closed.  Historical node ids are kept and now
# assert that nothing builds the engine, even when its classes are importable.


def _forbid_legacy_engine(monkeypatch):
    def _boom(*_args, **_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("archived legacy NexusEngine must not be constructed")

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _boom)


def _assert_archived(excinfo, entry):
    from nexus.engine.canonical_task_seam import LEGACY_ENGINE_ARCHIVED

    assert excinfo.value.entry == entry
    assert excinfo.value.reason == LEGACY_ENGINE_ARCHIVED == "archived_legacy_engine_2026-10-13"
    assert "ARCHIVED 2026-10-13 legacy-engine" in str(excinfo.value)


def test_build_command_service_constructs_engine_once(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError, build_command_service

    _forbid_legacy_engine(monkeypatch)
    with pytest.raises(LegacyEngineArchivedError) as excinfo:
        build_command_service(tmp_path)
    _assert_archived(excinfo, "build_command_service")


def test_build_engine_passes_config_overrides(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError, build_engine

    _forbid_legacy_engine(monkeypatch)
    with pytest.raises(LegacyEngineArchivedError) as excinfo:
        build_engine(tmp_path, benchmark_mode=True, silent=True)
    _assert_archived(excinfo, "build_engine")


def test_execute_single_task_via_service_uses_build_command_service(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import (
        LegacyEngineArchivedError,
        execute_single_task_via_service,
    )

    _forbid_legacy_engine(monkeypatch)
    with pytest.raises(LegacyEngineArchivedError) as excinfo:
        execute_single_task_via_service(
            "fix bug in parser", tmp_path, execution_context={"task_id": "t-1"}
        )
    _assert_archived(excinfo, "execute_single_task_via_service")


def test_build_legacy_cli_service_shapes_bug_request(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError, build_legacy_cli_service

    _forbid_legacy_engine(monkeypatch)
    with pytest.raises(LegacyEngineArchivedError) as excinfo:
        build_legacy_cli_service(tmp_path)
    _assert_archived(excinfo, "build_legacy_cli_service")


def test_build_legacy_cli_service_shapes_feature_request(monkeypatch, tmp_path):
    import nexus.engine.canonical_task_seam as seam

    # The adapter class that shaped bug/feature TaskRequests is gone with the engine.
    assert not hasattr(seam, "LegacyTaskServiceAdapter")
    _forbid_legacy_engine(monkeypatch)
    with pytest.raises(seam.LegacyEngineArchivedError):
        seam.build_legacy_cli_service(tmp_path)


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
        "audit the bounded runtime",
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
    assert set(request.route).isdisjoint({
        "provider",
        "model",
        "execution_topology",
        "recommended_flow",
    })
    assert request.route["workforce_bindings"]["online"]["worker_id"] == "grok_review"
    assert "provider" not in request.route["workforce_bindings"]["online"]
    assert result.production_ingress_count == 1
    assert result.production_runtime_entry_count == 1


def test_canonical_product_loads_governed_learning_policy_before_planner(
    monkeypatch,
    tmp_path,
):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    captured = {}

    def _runtime_budget(project_root, budget, **scope):
        captured["policy_root"] = project_root
        captured["policy_budget"] = budget
        captured["policy_scope"] = scope
        return {
            "learning_policy": {
                "episodic_memory_injection": {"enabled": True, "scope": "record_serialization"},
                "adoption_lineage": {"adoption_id": "ladopt:test", "status": "ACTIVE_CANDIDATE"},
            }
        }

    class _Gateway:
        def __init__(self, project_root):
            pass

        def ask_unified(self, request, **kwargs):
            captured["request"] = request
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {"execution_decision_authority": "CapabilityPlanner"},
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            _write_runtime_receipt(kwargs["receipt_path"], receipt)
            return receipt

    monkeypatch.setattr(
        "nexus.engine.learning_policy_loader.merge_runtime_learning_policy",
        _runtime_budget,
    )
    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", "qwen2.5-coder:7b")

    execute_canonical_product_task(
        "repair record_serialization for user profile",
        tmp_path,
        execution_context={
            "task_id": "canonical-learning-policy-1",
            "workspace_revision": "rev-current",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )

    assert captured["policy_root"] == tmp_path.resolve()
    assert captured["policy_scope"] == {
        "task_desc": "repair record_serialization for user profile",
        "target_model": "qwen2.5-coder:7b",
        "runtime_identity": "local_model_executor",
        "source_revision": "rev-current",
    }
    plan = captured["request"].canonical_planning_bundle.plan
    assert "memory" in plan.selected_capabilities
    assert (
        plan.signal_snapshot["learning_policy"]["adoption_lineage"]["adoption_id"] == "ladopt:test"
    )
    assert plan.signal_snapshot["route_truth_source"] == "CapabilityPlanner"
    assert (
        captured["request"].budget["learning_policy"]["adoption_lineage"]["adoption_id"]
        == "ladopt:test"
    )


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
        "repair target.py. Review the verified result.",
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
    assert request.codeintel["verify_commands"] == ["python -m py_compile target.py"]
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


def test_canonical_product_rejects_online_deny_when_no_local_channel(
    monkeypatch,
    tmp_path,
):
    import pytest

    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    class _UnexpectedGateway:
        def __init__(self, *args, **kwargs):
            raise AssertionError("gateway must not be constructed without a runtime channel")

    monkeypatch.setattr(
        "nexus.services.gateway.BattlesuitGateway",
        _UnexpectedGateway,
    )

    with pytest.raises(
        ValueError,
        match="canonical_product_no_execution_channel_enabled",
    ):
        execute_canonical_product_task(
            "audit runtime without an enabled execution channel",
            tmp_path,
            execution_context={
                "task_id": "canonical-no-runtime-channel",
                "workspace_revision": "rev-no-runtime-channel",
                "local_assist_mode": "disabled",
                "online_policy": "deny",
            },
        )


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


def _verified_campaign_test_identities(tmp_path, campaign_id):
    import hashlib

    from nexus.engine.canonical_task_seam import (
        VerifiedCampaignIdentity,
        VerifiedTaskCardIdentity,
    )

    task_id = "issue-982-wave-b3-governed-opencode-witness-20260919"
    canonical_card = tmp_path / "02-governed-opencode-runtime-witness.md"
    canonical_card.write_text(
        f"# Task Card: B3 test\ntask_id: `{task_id}`\ncampaign_id: `{campaign_id}`\n",
        encoding="utf-8",
    )
    task_card_hash = hashlib.sha256(canonical_card.read_bytes()).hexdigest()
    card = VerifiedTaskCardIdentity(
        task_id=task_id,
        task_card_path=(
            "tasks/github-issue-982-wave-b-20260919/02-governed-opencode-runtime-witness.md"
        ),
        canonical_task_card_path=str(canonical_card),
        task_card_hash=task_card_hash,
    )
    campaign = VerifiedCampaignIdentity(
        campaign_id=campaign_id,
        task_id=task_id,
        task_card_hash=task_card_hash,
    )
    return task_id, card, campaign


def test_b3_verified_campaign_projects_mimo_candidate_generation(tmp_path):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, campaign = _verified_campaign_test_identities(
        tmp_path,
        "github-issue-982-wave-b-20260919",
    )
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text="produce the bounded B3 OpenCode canary candidate",
        allowed_files=("README.md",),
        verifier_command=("python", "-m", "pytest"),
        task_card_identity=card,
        campaign_identity=campaign,
    )

    demand = result["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "bounded_candidate_generation"
    assert demand["minimum_autonomy"] == "L1"
    assert demand["context_class"] == "nexus_bounded"
    assert demand["mutation_intent"] is False
    assert result["binding"]["worker_id"] == "opencode_mimo_free"
    assert result["binding"]["provider"] == "opencode"
    assert result["binding"]["model"] == "opencode/mimo-v2.5-free"


def test_b3_campaign_text_without_verified_identity_does_not_mint_route(tmp_path):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, _campaign = _verified_campaign_test_identities(
        tmp_path,
        "github-issue-982-wave-b-20260919",
    )
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text="produce a bounded candidate",
        allowed_files=("README.md",),
        verifier_command=("python", "-m", "pytest"),
        task_card_identity=card,
    )

    demand = result["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "fast_bounded_implementation"
    assert demand["mutation_intent"] is True
    assert result["binding"]["worker_id"] == "agy_flash_38"


def test_b3_near_match_verified_campaign_does_not_select_mimo(tmp_path):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, campaign = _verified_campaign_test_identities(
        tmp_path,
        "github-issue-982-wave-b-20260919-suffix",
    )
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text="produce a bounded candidate",
        allowed_files=("README.md",),
        verifier_command=("python", "-m", "pytest"),
        task_card_identity=card,
        campaign_identity=campaign,
    )

    demand = result["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "fast_bounded_implementation"
    assert result["binding"]["worker_id"] == "agy_flash_38"


def test_external_intelligence_consumer_routes_to_chatgpt_web(tmp_path):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, _campaign = _verified_campaign_test_identities(
        tmp_path, "unrelated-campaign-20261012"
    )
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text="integration change for the bounded candidate",
        allowed_files=("README.md",),
        verifier_command=("python", "-m", "pytest"),
        task_card_identity=card,
        workforce_consumer="external_intelligence",
    )

    demand = result["workforce_demands"]["demands"][0]
    assert demand["requested_role"] == "bounded_candidate_generation"
    assert result["binding"]["worker_id"] == "opencli_chatgpt_advanced_web"
    assert result["binding"]["provider"] == "opencli_chatgpt"
    assert result["binding"]["model"] == "opencli_chatgpt/advanced"


def test_default_consumer_keeps_global_route_for_integration_text(tmp_path):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, _campaign = _verified_campaign_test_identities(
        tmp_path, "unrelated-campaign-20261012"
    )
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text="integration change for the bounded candidate",
        allowed_files=("README.md",),
        verifier_command=("python", "-m", "pytest"),
        task_card_identity=card,
    )

    demand = result["workforce_demands"]["demands"][0]
    # Since runtime #205 (S15) the seam's explicit bounded task_type ("repair") is authoritative:
    # a bare "integration" word in the text no longer escalates it to main_engineering.
    assert demand["requested_role"] == "fast_bounded_implementation"
    assert result["binding"]["worker_id"] == "agy_flash_38"


@pytest.mark.parametrize("consumer", ["unknown", "External_Intelligence", " ", None, 1])
def test_unknown_workforce_consumer_is_rejected_before_planning(tmp_path, consumer):
    from nexus.engine.canonical_task_seam import build_canonical_planner_admission

    task_id, card, _campaign = _verified_campaign_test_identities(
        tmp_path, "unrelated-campaign-20261012"
    )
    with pytest.raises(ValueError, match="canonical_workforce_consumer_unknown"):
        build_canonical_planner_admission(
            task_id=task_id,
            task_text="bounded change",
            allowed_files=("README.md",),
            verifier_command=("python", "-m", "pytest"),
            task_card_identity=card,
            workforce_consumer=consumer,
        )


class _StopAfterPlan(Exception):
    pass


def test_canonical_planner_admission_passes_repo_root_to_planning_seam(monkeypatch, tmp_path):
    import hashlib

    from nexus.core.repo_root import REPO_ROOT
    from nexus.engine.canonical_task_seam import (
        VerifiedTaskCardIdentity,
        build_canonical_planner_admission,
    )

    calls = []

    def spy(context, **kwargs):
        calls.append(kwargs)
        raise _StopAfterPlan

    monkeypatch.setattr("nexus.engine.canonical_execution.plan_canonical_task_bundle", spy)
    card_path = "tasks/campaign/root-1.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text("task_id: `root-1`\nAUTO_CHAIN: false\n", encoding="utf-8")
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", tmp_path
    )
    with pytest.raises(_StopAfterPlan):
        build_canonical_planner_admission(
            task_id="root-1",
            task_text="bounded change",
            allowed_files=("a.txt",),
            verifier_command=("true",),
            task_card_identity=VerifiedTaskCardIdentity(
                task_id="root-1",
                task_card_path=card_path,
                canonical_task_card_path=str(card.resolve()),
                task_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(),
            ),
        )
    assert calls == [{"shared_playbook_root": REPO_ROOT}]


def test_runtime_compat_plan_function_is_bound_to_repo_root(monkeypatch):
    """mainchain_entry plans through runtime_compat; its root is bound, not per call."""
    from nexus.core.repo_root import REPO_ROOT
    from nexus.services import runtime_compat

    seen = []
    from nexus_runtime.planning.engine.capability_planner import CapabilityPlanner as real

    class Spy(real):
        def __init__(self, *args, **kwargs):
            seen.append(kwargs.get("shared_playbook_root"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("nexus_runtime.support.engine.canonical_execution.CapabilityPlanner", Spy)
    context = runtime_compat.CanonicalTaskContext(
        task_id="bound-root-1",
        task_type="repair",
        task_desc="bound root witness",
        execution_world="local_armor",
        execution_channels=("online", "local"),
        task_facts={"mutation_requested": True, "candidate_required": True},
        authority_inputs={
            "direct_canonical_eligible": False,
            "isolation_required": True,
            "owner_authorized": False,
            "assisted_execution_required": False,
        },
        route_features={
            "bounded_allowed_file_count": 1,
            "deterministic_verifier_available": True,
        },
        codeintel={"target_file": "target.py"},
    )
    runtime_compat.plan_canonical_task_bundle(context)
    assert seen == [REPO_ROOT]
