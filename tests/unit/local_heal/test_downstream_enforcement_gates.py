from __future__ import annotations

import pytest
import os
from unittest import mock
from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutorRequest,
    _resolve_execution_topology,
    LocalModelExecutor,
)

def test_route_mode_freeze() -> None:
    expected_modes = {
        "CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY",
        "CLOUD_ASSISTED_BY_LOCAL_COMPACT_CONTEXT",
        "CLOUD_FIRST_LOCAL_GUARD_ADVISORY",
        "CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED",
        "LOCAL_FIRST_CLOUD_FALLBACK",
        "LOCAL_ONLY_PLANNED",
        "LOCAL_ONLY_BLOCKED",
        "LOCAL_ONLY_EXECUTED",
    }
    current_modes = {m.name for m in RouteMode}
    assert current_modes == expected_modes, f"Detected unexpected RouteModes: {current_modes - expected_modes}"

def test_resolve_execution_topology_no_fallback() -> None:
    req_empty = LocalModelExecutorRequest(
        task_id="t1",
        problem_statement="prob",
        repo_root=".",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={},
    )
    with pytest.raises(ValueError, match="Missing signal_snapshot in route_context"):
        _resolve_execution_topology(req_empty)

def test_resolve_execution_topology_strict_success() -> None:
    req = LocalModelExecutorRequest(
        task_id="t1",
        problem_statement="prob",
        repo_root=".",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "planner_topology",
                "protocol_mode": "anchored_edit",
                "executor_model": "some_model"
            }
        },
    )
    assert _resolve_execution_topology(req) == "planner_topology"

def test_executor_fail_closed_on_missing_model_or_protocol() -> None:
    # 缺 protocol_mode 應拋出 ValueError
    req_no_protocol = LocalModelExecutorRequest(
        task_id="t2",
        problem_statement="prob",
        repo_root=".",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "executor_model": "some_model"
            }
        },
    )
    with pytest.raises(ValueError, match="Missing protocol_mode in signal_snapshot"):
        _resolve_execution_topology(req_no_protocol)

    # 缺 executor_model 且不是 committee 應拋出 ValueError
    req_no_model = LocalModelExecutorRequest(
        task_id="t3",
        problem_statement="prob",
        repo_root=".",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit"
            }
        },
    )
    with pytest.raises(ValueError, match="Missing executor_model in signal_snapshot"):
        _resolve_execution_topology(req_no_model)

def test_committee_orchestrator_rejects_env_and_hardcoded_specs() -> None:
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
    from pathlib import Path

    op = OperationalContext(
        instance_id="inst-1",
        repo_dir=Path("."),
        problem_statement="prob",
        route_context={}  # 缺少 signal_snapshot
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)

    with mock.patch("nexus.services.local_heal.committee_orchestrator.HealOrchestrator.__init__", lambda *a, **k: None):
        orchestrator = CommitteeOrchestrator()
    
    with mock.patch.dict(os.environ, {"NEXUS_USE_COMMITTEE": "1"}):
        with mock.patch("nexus.services.local_heal.committee_orchestrator.HealOrchestrator.run") as mock_super_run:
            mock_super_run.return_value = ctx
            res = orchestrator.run(ctx)
            assert mock_super_run.called
            assert res == ctx

    # 若設定了 local_committee_enabled 但缺少 proposer_specs，應拋出 ValueError (fail closed)
    op_active = OperationalContext(
        instance_id="inst-1",
        repo_dir=Path("."),
        problem_statement="prob",
        route_context={
            "signal_snapshot": {
                "local_committee_enabled": True
                # 缺少 proposer_specs
            }
        }
    )
    ctx_active = HealContext(op=op_active, gov=gov)
    with pytest.raises(ValueError, match="Missing proposer_specs in signal_snapshot"):
        orchestrator.run(ctx_active)

def test_local_committee_candidate_provider_rejects_defaults() -> None:
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.local_model_provider import InertLocalModelProvider
    
    provider = InertLocalModelProvider()
    
    # 缺 proposer_specs 拋出 ValueError
    with pytest.raises(ValueError, match="Missing proposer_specs in signal_snapshot"):
        LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t4",
            problem_statement="prob",
            target_file="file.py",
            target_symbol="func",
            locked_search="span",
            evidence_refs=(),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context={
                "signal_snapshot": {
                    "judge_model": "qwen2.5:3b"
                }
            }
        )

    # 缺 judge_model 拋出 ValueError
    with pytest.raises(ValueError, match="Missing judge_model in signal_snapshot"):
        LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t4",
            problem_statement="prob",
            target_file="file.py",
            target_symbol="func",
            locked_search="span",
            evidence_refs=(),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context={
                "signal_snapshot": {
                    "proposer_specs": [{"model": "model-1", "role": "primary"}]
                }
            }
        )

def test_capability_adapter_rejects_missing_snapshot_and_freezes_route_truth() -> None:
    from nexus.services.local_heal.capability_adapter import LocalHealCapabilityAdapter, LocalHealCapabilityRequest
    
    req = LocalHealCapabilityRequest(
        task_id="t5",
        problem_statement="prob",
        evidence_refs=(),
        executor_controls={"enable_local_heal": True, "local_heal_mode": "candidate"},
        dry_run=False,
    )
    
    # 缺失 snapshot 時，應直接回傳 fail-closed 決策，RouteMode 為 LOCAL_ONLY_BLOCKED
    res = LocalHealCapabilityAdapter.run(req)
    assert res.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert res.hybrid_route.authority == Authority.FAIL_CLOSED
    assert res.hybrid_route.route_truth_source == "CapabilityPlanner"
    
    # 驗證即使 controls 試圖 override route_truth_source，也必須無效 (永遠為 CapabilityPlanner)
    req_override = LocalHealCapabilityRequest(
        task_id="t5",
        problem_statement="prob",
        evidence_refs=(),
        executor_controls={
            "enable_local_heal": True, 
            "local_heal_mode": "candidate",
            "route_truth_source": "AdversarySource",
            "route_context": {
                "signal_snapshot": {
                    "enable_pipeline": True,
                    "model_call_allowed": True,
                }
            }
        },
        dry_run=False,
    )
    # 由於 os.environ 中有 fail_closed 模擬等，我們 mock 掉 runtime policy
    with mock.patch("nexus.services.local_heal.capability_adapter.build_local_heal_runtime_policy") as mock_policy:
        from nexus.services.local_heal.capability_runtime_policy import LocalHealRuntimePolicy
        mock_policy.return_value = LocalHealRuntimePolicy(
            enable_pipeline=True,
            mutation_allowed=True,
            public_claim_allowed=False,
            production_ready=False,
            model_call_allowed=True,
            provider_call_allowed=True,
            network_allowed=False,
            dry_run=False
        )
        res_override = LocalHealCapabilityAdapter.run(req_override)
        assert res_override.hybrid_route.route_truth_source == "CapabilityPlanner"

def test_no_global_env_mutation_during_normalization() -> None:
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    
    req = LocalModelExecutorRequest(
        task_id="t6",
        problem_statement="prob",
        repo_root=".",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
    )
    
    # 確保 NEXUS_PROTOCOL_MODE 環境變數在 _normalize_candidate_patch 執行前後均不被修改
    os.environ["NEXUS_PROTOCOL_MODE"] = "standard"
    try:
        patch = "<<<<<<< REPLACE\nprint('hello')\n>>>>>>> REPLACE"
        _normalize_candidate_patch(req, "print('old')", patch)
        assert os.environ.get("NEXUS_PROTOCOL_MODE") == "standard"
    finally:
        os.environ.pop("NEXUS_PROTOCOL_MODE", None)
