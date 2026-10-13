"""Core-bound repair continuation (EIA open_swe worker path).

A unit whose first bound repair fails unit verification continues in the same
runtime session.  The continuation reuses the parent's Core binding (it never mints
a new one), the runtime must attest the same BOUND identity, and closure only
accepts a repaired receipt that stays bound to the parent's binding.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.services.external_intelligence_closure import (
    UNIT_VERIFICATION_SCHEMA,
    ClosureError,
    _receipt_identity,
    _validate_repair_result,
    build_unit_repair_delta,
    validate_worker_receipt,
)
from nexus.services.external_intelligence_core_binding import (
    FRESHNESS_MARGIN_SECONDS,
    CoreBindingError,
    binding_hash_for,
    binding_validity_seconds,
    parse_bound_execution_envelope_v2,
    validate_repository_mutation_binding,
)
from nexus.services.external_intelligence_fanout import (
    AdaptiveWorkerFanoutRuntime,
    CapacityLease,
    FanoutError,
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeRunResult,
)
from tests.services.test_external_intelligence_core_binding import (
    ORIGIN,
    REPOSITORY,
    TARGET,
    bound_unit_mapping,
    make_bound_repo,
)
from tests.services.test_open_swe_worker_transport import _completed

SESSION = "ses_open_swe_1234567890abcdef1234"


def failing_unit_verification(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": UNIT_VERIFICATION_SCHEMA,
        "status": "FAIL",
        "verification_id": "9" * 64,
        "worker_receipt_id": receipt["receipt_id"],
        "task_id": receipt["task_id"],
        "unit_id": receipt["unit_id"],
        "results": [
            {
                "verifier_id": "unit-pytest",
                "passed": False,
                "returncode": 1,
                "stdout_sha256": "1" * 64,
                "stderr_sha256": "2" * 64,
                "error": "",
            }
        ],
    }


def write_repair_delta(receipt: dict[str, Any], directory: Path) -> tuple[str, str]:
    """Persist the production unit repair delta for a failed unit verification."""
    delta = build_unit_repair_delta(receipt, failing_unit_verification(receipt), repair_index=1)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "task-1--u1--001.json"
    raw = json.dumps(delta, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return str(path), hashlib.sha256(raw).hexdigest()


def _bound_open_swe(
    tmp_path: Path,
    monkeypatch,
    *,
    continue_status: str = "BOUND",
    continue_hashes: tuple[str, str] | None = None,
    max_repairs_per_unit: int = 1,
) -> SimpleNamespace:
    import nexus.services.open_swe_external_intelligence as module

    scenario = make_bound_repo(tmp_path)
    unit = bound_unit_mapping(tmp_path, scenario)
    calls: list[dict[str, Any]] = []

    def runtime_call(_executable, payload, **_kwargs):
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        calls.append(json.loads(json.dumps(payload)))
        target = Path(payload["workspace_path"]) / TARGET
        if payload["operation"] in {"worker_run", "worker_continue"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            body = "assert True" if payload["operation"] == "worker_run" else "assert 1 == 1"
            target.write_text(f"def test_bound():\n    {body}\n", encoding="utf-8")
        result = _completed(module, payload)
        supplied = (payload.get("core_binding_hash"), payload.get("acceptance_contract_hash"))
        status = "BOUND"
        returned = supplied
        if payload["operation"] == "worker_continue":
            status = continue_status
            returned = continue_hashes or supplied
        result.update(
            core_binding_status=status,
            core_binding_hash=returned[0] or "",
            acceptance_contract_hash=returned[1] or "",
        )
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
    )
    store = FanoutStore(tmp_path / "state")
    runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(scenario.repo, tmp_path / "workspaces"),
        store=store,
        transport=transport,
        max_repairs_per_unit=max_repairs_per_unit,
    )
    first = runtime.run([unit], CapacityLease(1, 1, 1, 1))
    assert first["errors"] == {}
    receipt = first["receipts"]["u1"]
    assert receipt["core_binding_status"] == "BOUND"
    ref, sha = write_repair_delta(receipt, tmp_path / "closure" / "repair-deltas")
    return SimpleNamespace(
        runtime=runtime,
        store=store,
        transport=transport,
        module=module,
        calls=calls,
        receipt=receipt,
        repair_ref=ref,
        repair_sha256=sha,
    )


def _continue(ctx: SimpleNamespace, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    return ctx.runtime.continue_repair(
        receipt or ctx.receipt,
        repair_id="d001",
        repair_ref=ctx.repair_ref,
        repair_sha256=ctx.repair_sha256,
    )


def _repair_attempt(ctx: SimpleNamespace) -> dict[str, Any]:
    return json.loads((ctx.store.attempts / "task-1--u1--repair-d001.json").read_text("utf-8"))


def test_bound_repair_continuation_stays_bound_to_parent_binding(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    parent = ctx.receipt
    parent_bound = validate_worker_receipt(parent)

    repaired = _continue(ctx)

    continue_calls = [call for call in ctx.calls if call["operation"] == "worker_continue"]
    assert len(continue_calls) == 1
    payload = continue_calls[0]
    assert payload["session_id"] == parent["session_id"] == SESSION
    assert payload["artifact_path"] == str(Path(ctx.repair_ref).resolve())
    assert payload["core_binding_hash"] == parent["core_binding_hash"]
    assert payload["acceptance_contract_hash"] == parent["acceptance_contract_hash"]
    assert "attempt_id" not in payload
    assert payload["operation_id"] != parent["operation_id"]
    assert f"\nrepair_sha256={ctx.repair_sha256}\n" in payload["prompt"]
    assert f"\nparent_candidate_commit={parent['candidate_commit']}\n" in payload["prompt"]

    assert repaired["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert repaired["mode"] == "REPAIR_CONTINUE"
    assert repaired["operation_id"] == payload["operation_id"]
    assert repaired["core_binding_status"] == "BOUND"
    for field in (
        "bound_envelope_ref",
        "bound_envelope_sha256",
        "core_binding_hash",
        "acceptance_contract_hash",
    ):
        assert repaired[field] == parent[field]
    assert repaired["core_binding_operation_id"] == parent["operation_id"]
    assert repaired["core_binding_attempt_id"] == parent["attempt_id"]
    assert repaired["parent_commit"] == parent["candidate_commit"]
    _semantic, binding, _sha = parse_bound_execution_envelope_v2(
        Path(parent["bound_envelope_ref"]).read_text(encoding="utf-8"),
        semantic_envelope_sha256=parent["envelope_sha256"],
    )
    assert binding["operation_id"] == parent["operation_id"]

    attempt = _repair_attempt(ctx)
    assert attempt["state"] == "COMPLETED"
    assert attempt["core_binding_hash"] == parent["core_binding_hash"]
    assert attempt["core_binding_operation_id"] == parent["operation_id"]

    repaired_bound = validate_worker_receipt(repaired)
    assert repaired_bound["core_binding_status"] == "BOUND"
    assert repaired_bound["core_binding_operation_id"] == parent["operation_id"]
    _validate_repair_result(parent_bound, repaired)


@pytest.mark.parametrize(
    ("continue_status", "continue_hashes"),
    [
        ("LEGACY_UNBOUND", ("", "")),
        ("BOUND", ("sha256:" + "9" * 64, "sha256:" + "8" * 64)),
    ],
)
def test_non_bound_continuation_result_for_bound_attempt_is_outcome_unknown(
    tmp_path, monkeypatch, continue_status, continue_hashes
):
    ctx = _bound_open_swe(
        tmp_path, monkeypatch, continue_status=continue_status, continue_hashes=continue_hashes
    )
    with pytest.raises(FanoutError, match="FANOUT_RECONCILIATION_REQUIRED"):
        _continue(ctx)
    attempt = _repair_attempt(ctx)
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["transport_status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert not (ctx.store.receipts / "task-1--u1--repair-d001.json").exists()


class _CompletedNonBoundContinuation:
    """A transport that returns COMPLETED without re-checking the Core attestation."""

    supports_core_mutation_binding = True

    def __init__(self, inner: Any, *, core_status: str, core_hash: str | None = None):
        self.inner = inner
        self.core_status = core_status
        self.core_hash = core_hash
        self.provider_id = inner.provider_id
        self.model_id = inner.model_id
        self.model = inner.model
        self.continued: list[dict[str, Any]] = []

    def bind_worker(self, worker):
        self.inner.bind_worker(worker)
        return self

    def prepare_operation_id(self, *args, **kwargs):
        return self.inner.prepare_operation_id(*args, **kwargs)

    def continue_session(self, **kwargs):
        self.continued.append(dict(kwargs))
        workspace = Path(kwargs["workspace_path"])
        (workspace / TARGET).write_text("def test_bound():\n    pass\n", encoding="utf-8")
        core = kwargs["core_binding"]
        return OpenCodeRunResult(
            status="COMPLETED",
            worker_backend="open_swe",
            session_id=kwargs["session_id"],
            response_text=json.dumps({
                "schema": "external_intelligence_worker_result.v1",
                "task_id": "task-1",
                "unit_id": "u1",
                "status": "IMPLEMENTATION_COMPLETED",
                "summary": "repaired",
            }),
            provider_id=self.provider_id,
            model_id=self.model_id,
            directory=str(workspace.resolve()),
            process_started=True,
            operation_id=kwargs["operation_id"],
            core_binding_status=self.core_status,
            core_binding_hash=self.core_hash or core["core_binding_hash"],
            acceptance_contract_hash=core["acceptance_contract_hash"],
        )


@pytest.mark.parametrize(
    ("core_status", "core_hash"),
    [("LEGACY_UNBOUND", None), ("BOUND", "sha256:" + "7" * 64)],
)
def test_fanout_rejects_completed_non_bound_continuation_independently(
    tmp_path, monkeypatch, core_status, core_hash
):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    ctx.runtime.transport = _CompletedNonBoundContinuation(
        ctx.transport, core_status=core_status, core_hash=core_hash
    )
    with pytest.raises(FanoutError, match="CORE_BINDING_ATTESTATION_MISMATCH"):
        _continue(ctx)
    attempt = _repair_attempt(ctx)
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["transport_status"] == "CORE_BINDING_ATTESTATION_MISMATCH"
    assert not (ctx.store.receipts / "task-1--u1--repair-d001.json").exists()


def test_tampered_bound_envelope_blocks_continuation_before_effect(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    bound_path = Path(ctx.receipt["bound_envelope_ref"])
    bound = json.loads(bound_path.read_text(encoding="utf-8"))
    bound["repository_mutation_binding"]["integration_authority"]["execution_lane"] = (
        "DIRECT_CANONICAL"
    )
    bound_path.write_text(json.dumps(bound), encoding="utf-8")
    with pytest.raises(
        FanoutError, match="CORE_BINDING_REVALIDATION_FAILED:CORE_BOUND_ENVELOPE_BINDING_INVALID"
    ):
        _continue(ctx)
    assert [call for call in ctx.calls if call["operation"] == "worker_continue"] == []
    assert not (ctx.store.attempts / "task-1--u1--repair-d001.json").exists()


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda r: r.pop("core_binding_hash"), "CORE_BINDING_PARENT_RECEIPT_INVALID"),
        (lambda r: r.update(core_binding_status="LEGACY_UNBOUND"), "PARENT_RECEIPT_INVALID"),
        (
            lambda r: r.update(core_binding_hash="sha256:" + "9" * 64),
            "CORE_BINDING_REVALIDATION_FAILED:core_binding_hash",
        ),
        (
            lambda r: r.update(operation_id="0" * 64),
            "CORE_BINDING_REVALIDATION_FAILED:core_binding_operation",
        ),
        (
            lambda r: r.update(mutation_paths=["tests/other.py"]),
            "CORE_BINDING_REVALIDATION_FAILED:core_binding_scope",
        ),
    ],
)
def test_mismatched_or_partial_parent_binding_is_rejected_before_effect(
    tmp_path, monkeypatch, mutate, error
):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    receipt = json.loads(json.dumps(ctx.receipt))
    mutate(receipt)
    with pytest.raises(FanoutError, match=error):
        _continue(ctx, receipt)
    assert [call for call in ctx.calls if call["operation"] == "worker_continue"] == []
    assert not (ctx.store.attempts / "task-1--u1--repair-d001.json").exists()


def test_bound_continuation_transport_contract(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    core = {
        "core_binding_hash": ctx.receipt["core_binding_hash"],
        "acceptance_contract_hash": ctx.receipt["acceptance_contract_hash"],
    }
    workspace = ctx.receipt["workspace_path"]
    with pytest.raises(FanoutError, match="CORE_BINDING_CONTINUATION_MATERIAL_FORBIDDEN"):
        ctx.transport._request(
            "worker_continue",
            session_id=SESSION,
            prompt="x",
            artifact_path=ctx.repair_ref,
            workspace_path=workspace,
            operation_material={"schema": "x"},
            core_binding=core,
        )
    with pytest.raises(FanoutError, match="CORE_BINDING_HASHES_REQUIRED"):
        ctx.transport.continue_session(
            session_id=SESSION,
            prompt="x",
            artifact_path=ctx.repair_ref,
            workspace_path=workspace,
            core_binding={"core_binding_hash": "", "acceptance_contract_hash": ""},
        )

    repaired = _continue(ctx)
    ctx.calls.clear()
    reconciled = ctx.transport.reconcile_workspace(
        workspace_path=workspace, operation_id=repaired["operation_id"], core_binding=core
    )
    assert reconciled.core_binding_status == "BOUND"
    (payload,) = ctx.calls
    assert payload["operation"] == "worker_reconcile"
    assert payload["operation_id"] == repaired["operation_id"]
    assert payload["artifact_path"] == ""
    assert payload["core_binding_hash"] == core["core_binding_hash"]
    assert payload["acceptance_contract_hash"] == core["acceptance_contract_hash"]


def test_unbound_parent_continuation_sends_no_core_binding(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    ctx.calls.clear()
    result = ctx.transport.continue_session(
        session_id=SESSION,
        prompt="task_id=task-1\nunit_id=u1",
        artifact_path=ctx.repair_ref,
        workspace_path=ctx.receipt["workspace_path"],
    )
    (payload,) = ctx.calls
    assert "core_binding_hash" not in payload
    assert "acceptance_contract_hash" not in payload
    assert result.status == "COMPLETED"


def _rehash(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["receipt_id"] = _receipt_identity(receipt)
    return receipt


def test_closure_rejects_repair_that_drops_or_changes_the_parent_binding(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    parent_bound = validate_worker_receipt(ctx.receipt)
    repaired = _continue(ctx)

    unbound = {
        key: value
        for key, value in repaired.items()
        if key
        not in {
            "bound_envelope_ref",
            "bound_envelope_sha256",
            "core_binding_status",
            "core_binding_hash",
            "acceptance_contract_hash",
            "core_binding_operation_id",
            "core_binding_attempt_id",
        }
    }
    with pytest.raises(ClosureError, match="REPAIR_CORE_BINDING_MISMATCH"):
        _validate_repair_result(parent_bound, _rehash(unbound))

    missing_root = dict(repaired)
    missing_root.pop("core_binding_operation_id")
    with pytest.raises(ClosureError, match="CORE_BINDING_RECEIPT_INVALID"):
        validate_worker_receipt(_rehash(missing_root))

    wrong_root = {**repaired, "core_binding_operation_id": "0" * 64}
    with pytest.raises(ClosureError, match="CORE_BINDING_RECEIPT_MISMATCH"):
        validate_worker_receipt(_rehash(wrong_root))

    initial_with_root = {**ctx.receipt, "core_binding_operation_id": ctx.receipt["operation_id"]}
    with pytest.raises(ClosureError, match="CORE_BINDING_RECEIPT_INVALID"):
        validate_worker_receipt(_rehash(initial_with_root))


def test_continuation_revalidation_enforces_window_and_creation_time(tmp_path, monkeypatch):
    ctx = _bound_open_swe(tmp_path, monkeypatch)
    receipt = ctx.receipt
    _semantic, binding, _sha = parse_bound_execution_envelope_v2(
        Path(receipt["bound_envelope_ref"]).read_text(encoding="utf-8"),
        semantic_envelope_sha256=receipt["envelope_sha256"],
    )
    workspace = Path(receipt["workspace_path"])
    tree = subprocess.run(
        ["git", "rev-parse", f"{receipt['base_sha']}^{{tree}}"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    kwargs: dict[str, Any] = {
        "operation_id": receipt["operation_id"],
        "attempt_id": receipt["attempt_id"],
        "repository": REPOSITORY,
        "expected_base": receipt["base_sha"],
        "observed_origin": ORIGIN,
        "observed_base_tree": tree,
        "workspace_path": workspace,
        "allowed_paths": [TARGET],
    }
    validate_repository_mutation_binding(binding, continuation=True, **kwargs)
    later = datetime.now(timezone.utc) + timedelta(days=1)
    for continuation in (False, True):
        with pytest.raises(CoreBindingError, match="core_binding_freshness"):
            validate_repository_mutation_binding(
                binding, now=later, continuation=continuation, **kwargs
            )
    earlier = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(CoreBindingError, match="core_binding_freshness"):
        validate_repository_mutation_binding(binding, now=earlier, continuation=True, **kwargs)
    open_ended = json.loads(json.dumps(binding))
    open_ended["freshness"]["valid_until"] = None
    open_ended["binding_hash"] = binding_hash_for(open_ended)
    validate_repository_mutation_binding(open_ended, **kwargs)
    with pytest.raises(CoreBindingError, match="core_binding_freshness"):
        validate_repository_mutation_binding(open_ended, continuation=True, **kwargs)


def test_binding_validity_covers_initial_run_plus_repair_budget():
    assert binding_validity_seconds(300, 0) == 300 * 1 + FRESHNESS_MARGIN_SECONDS
    assert binding_validity_seconds(300, 1) == 300 * 2 + FRESHNESS_MARGIN_SECONDS
    assert binding_validity_seconds(900.0, 20) == 900 * 21 + FRESHNESS_MARGIN_SECONDS
    for budget in (-1, 21, True, 1.0):
        with pytest.raises(CoreBindingError, match="CORE_REPAIR_BUDGET_INVALID"):
            binding_validity_seconds(300, budget)  # type: ignore[arg-type]
    with pytest.raises(CoreBindingError, match="CORE_FRESHNESS_WINDOW_INVALID"):
        binding_validity_seconds(0, 1)


@pytest.mark.parametrize("budget", [0, 1, 3])
def test_minted_binding_lifetime_follows_fanout_repair_budget(tmp_path, monkeypatch, budget):
    ctx = _bound_open_swe(tmp_path, monkeypatch, max_repairs_per_unit=budget)
    _semantic, binding, _sha = parse_bound_execution_envelope_v2(
        Path(ctx.receipt["bound_envelope_ref"]).read_text(encoding="utf-8"),
        semantic_envelope_sha256=ctx.receipt["envelope_sha256"],
    )
    created = datetime.fromisoformat(binding["freshness"]["created_at"].replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(binding["freshness"]["valid_until"].replace("Z", "+00:00"))
    expected = ctx.transport.timeout * (1 + budget) + FRESHNESS_MARGIN_SECONDS
    assert (deadline - created).total_seconds() == expected


def test_expired_binding_blocks_continuation_before_effect(tmp_path, monkeypatch):
    import nexus.services.external_intelligence_core_binding as core_binding

    ctx = _bound_open_swe(tmp_path, monkeypatch)
    real_datetime = core_binding.datetime

    class _Later(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(core_binding, "datetime", _Later)
    with pytest.raises(
        FanoutError, match="CORE_BINDING_REVALIDATION_FAILED:core_binding_freshness"
    ):
        _continue(ctx)
    assert [call for call in ctx.calls if call["operation"] == "worker_continue"] == []
    assert not (ctx.store.attempts / "task-1--u1--repair-d001.json").exists()


def test_repair_budgets_must_agree_between_closure_and_worker_runtime(tmp_path):
    from nexus.services.external_intelligence_closure import (
        ClosureStore,
        CompositionWorkspaceAllocator,
        ExternalIntelligenceClosureRuntime,
    )

    scenario = make_bound_repo(tmp_path)
    with pytest.raises(FanoutError, match="INVALID_REPAIR_BUDGET"):
        AdaptiveWorkerFanoutRuntime(
            allocator=GitWorktreeAllocator(scenario.repo, tmp_path / "ws"),
            store=FanoutStore(tmp_path / "state"),
            max_repairs_per_unit=21,
        )
    worker = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(scenario.repo, tmp_path / "ws"),
        store=FanoutStore(tmp_path / "state"),
        max_repairs_per_unit=2,
    )

    def closure(budget: int) -> ExternalIntelligenceClosureRuntime:
        return ExternalIntelligenceClosureRuntime(
            repository_root=scenario.repo,
            allocator=CompositionWorkspaceAllocator(scenario.repo, tmp_path / "closure"),
            store=ClosureStore(tmp_path / "closure-state"),
            c_runtime=worker,
            max_repairs_per_unit=budget,
        )

    assert closure(2).max_repairs_per_unit == 2
    with pytest.raises(ClosureError, match="REPAIR_BUDGET_EXCEEDS_WORKER_BUDGET"):
        closure(3)
