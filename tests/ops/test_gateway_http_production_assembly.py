"""Regression coverage for the source-owned production writer assembly seam."""

import hashlib
from dataclasses import replace

import pytest

from nexus.contracts.state_owner_transition import WriterTransitionRequest
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.state_owner_transition_service import (
    StateOwnerTransitionService,
    TransitionServiceError,
)
from nexus.orchestrator.unified_mcp_gateway import (
    LoadedWriterCollectorPlan,
    UnifiedMCPGateway,
)
from nexus.orchestrator.writer_activation_assembly import (
    WriterAssemblyError,
    load_writer_assembly,
)
from tests.nexus.orchestrator.test_state_owner_transition_service import _setup


def _loaded_vector(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    request = WriterTransitionRequest.from_mapping(raw)
    plan = LoadedWriterCollectorPlan(
        request_digest=request.request_digest,
        cohort_id="initial-cohort",
        root_id=request.root_id,
        root=root.resolve(),
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        generation=0,
        writer_id="legacy-observer",
        source_receipt=(tmp_path / "source.receipt").resolve(),
        snapshot_receipt=(tmp_path / "snapshot.receipt").resolve(),
        rollback_receipt=(tmp_path / "rollback.receipt").resolve(),
        writer_plan_receipt=(tmp_path / "writer-plan.receipt").resolve(),
        artifacts=("state.json",),
    )
    return root, source_root, source, request, plan


def _real_gateway(tmp_path, source):
    root = tmp_path / "gateway-root"
    root.mkdir()
    service = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)
    gateway = UnifiedMCPGateway(service=service)
    assert gateway.bootstrap_writer_admission() == "HELD"
    return root, service, gateway


def test_loaded_assembly_accepts_real_two_role_vector(tmp_path, monkeypatch):
    root, source_root, source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    second_root = tmp_path / "runtime"
    second_root.mkdir()
    second_request = replace(
        request,
        root_id="runtime",
        expected_root_identity=hashlib.sha256(str(second_root.resolve()).encode()).hexdigest(),
    )
    second_plan = replace(
        plan,
        request_digest=second_request.request_digest,
        root_id="runtime",
        root=second_root.resolve(),
        writer_id="legacy-runtime-observer",
    )
    assembly = load_writer_assembly(
        source_root=source_root.resolve(),
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        plans=(plan, second_plan),
        requests=(request, second_request),
    )
    assert assembly.ordered_roots == (root.resolve(), second_root.resolve())
    assert assembly.plan_for(second_request) is second_plan


def test_loaded_assembly_rejects_duplicate_root(tmp_path, monkeypatch):
    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    with pytest.raises(WriterAssemblyError, match="ASSEMBLY_ROOTS_NOT_UNIQUE"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=request.expected_source_head,
            source_tree=request.expected_source_tree,
            plans=(plan, plan),
            requests=(request, request),
        )


def test_loaded_assembly_rejects_duplicate_request_digest(tmp_path, monkeypatch):
    _root, source_root, _source, request, plan = _loaded_vector(tmp_path, monkeypatch)
    second_root = tmp_path / "runtime"
    second_root.mkdir()
    second_request = replace(
        request,
        root_id="runtime",
        expected_root_identity=hashlib.sha256(str(second_root.resolve()).encode()).hexdigest(),
    )
    duplicate_request = object.__new__(type("_DuplicateDigestRequest", (WriterTransitionRequest,), {}))
    for field in WriterTransitionRequest.__dataclass_fields__:
        object.__setattr__(duplicate_request, field, getattr(second_request, field))
    duplicate_request.__class__.request_digest = property(lambda self: request.request_digest)
    second_plan = replace(
        plan,
        root_id="runtime",
        root=second_root.resolve(),
        writer_id="legacy-runtime-observer",
        # A duplicated digest must never make by_request_digest ambiguous.
        request_digest=plan.request_digest,
    )
    with pytest.raises(WriterAssemblyError, match="DIGEST"):
        load_writer_assembly(
            source_root=source_root.resolve(),
            source_head=request.expected_source_head,
            source_tree=request.expected_source_tree,
            plans=(plan, second_plan),
            requests=(request, duplicate_request),
        )


def test_transition_binds_real_gateway_collector_port(tmp_path, monkeypatch):
    _root, source_root, source, request, _plan = _loaded_vector(tmp_path, monkeypatch)
    root, service, gateway = _real_gateway(tmp_path, source)
    transition_service = StateOwnerTransitionService(
        roots={request.root_id: root},
        source=source,
        source_root=source_root,
        service=service,
    )
    transition_service.bind_collector_port(gateway._writer_transition_collector)
    assert transition_service._collector_port.__self__ is gateway


def test_transition_rejects_wrong_service_and_arbitrary_callback(tmp_path, monkeypatch):
    _root, source_root, source, request, _plan = _loaded_vector(tmp_path, monkeypatch)
    root, first, first_gateway = _real_gateway(tmp_path, source)
    other_root = tmp_path / "other"
    other_root.mkdir()
    second = SelfHostedTaskService(other_root, ephemeral=True, auto_reconcile=False)
    second_gateway = UnifiedMCPGateway(service=second)
    assert second_gateway.bootstrap_writer_admission() == "HELD"
    transition_service = StateOwnerTransitionService(
        roots={request.root_id: root},
        source=source,
        source_root=source_root,
        service=first,
    )
    with pytest.raises(TransitionServiceError, match="COLLECTOR_PORT_SERVICE_MISMATCH"):
        transition_service.bind_collector_port(second_gateway._writer_transition_collector)
    with pytest.raises(TypeError, match="source-owned collector port"):
        transition_service.bind_collector_port(lambda _request: {})
