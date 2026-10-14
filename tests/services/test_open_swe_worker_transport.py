from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.external_intelligence_closure import ClosureError, validate_worker_receipt
from nexus.services.external_intelligence_fanout import (
    AdaptiveWorkerFanoutRuntime,
    CapacityLease,
    FanoutError,
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeRunResult,
)


@pytest.fixture(autouse=True)
def _runtime_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _prompt() -> str:
    return "\n".join([
        "task_id=task-1",
        "unit_id=u1",
        'authorized_mutation_paths=["a.py"]',
        "bounded task",
    ])


def _worker():
    return {
        "worker_id": "google/gemini-worker-a",
        "provider": "google_genai",
        "model": "google_genai/gemini-test",
        "role_ceiling": "bounded repair",
        "admission_evidence_ref": "admission-a",
        "admission_evidence_hash": "a" * 64,
        "selection_evidence_ref": "selection-a",
        "selection_evidence_hash": "b" * 64,
    }


def _artifact_and_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"failure":"VALUE must be 2"}\n', encoding="utf-8")
    return workspace, artifact


def _hash_json(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _projected_pair(operation_id: str):
    authorization_material = {
        "schema": "nexus.runtime.effect_authorization.v1",
        "authority_id": "owner-wave4",
        "authority_ref": "Nexus-new#1007",
        "operation_id": operation_id,
        "attempt_id": "attempt-wave4-open-swe",
        "repository": "James3014/Nexus-new",
        "source_revision": "1" * 40,
        "base_revision": "1" * 40,
        "workspace_id": "workspace-wave4",
        "target_id": "target-wave4",
        "expires_at": None,
        "effects": {
            "filesystem": {"write_paths": ["a.py"]},
            "process": {"commands": []},
            "network": {"hosts": []},
            "git": {"operations": []},
        },
    }
    authorization = {
        **authorization_material,
        "authorization_hash": _hash_json(authorization_material),
    }
    projection_material = {
        "schema": "nexus.runtime.tool_projection_manifest.v1",
        "authorization_hash": authorization["authorization_hash"],
        "operation_id": operation_id,
        "attempt_id": authorization["attempt_id"],
        "provider": "google_genai",
        "backend_id": "nexus-open-swe-runtime",
        "selected_tools": [
            "read_file",
            "record_diagnosis",
            "record_worker_result",
            "write_file",
        ],
        "selected_effects": {"filesystem": {"write_paths": ["a.py"]}},
        "authority_kind": "DERIVED_PROJECTION_ONLY",
    }
    projection = {
        **projection_material,
        "projection_hash": _hash_json(projection_material),
    }
    return authorization, projection


def _completed(module, payload, *, response_status="IMPLEMENTATION_COMPLETED"):
    if payload["operation"] == "identity":
        return {
            "schema": module.PROTOCOL_RESULT_SCHEMA,
            "kind": "identity",
            "status": "IDENTIFIED",
            "distribution_name": "nexus-open-swe-runtime",
            "distribution_version": "0.1.0",
            "runtime_protocol_version": module.PROTOCOL_REQUEST_SCHEMA,
            "artifact_identity": {
                "module_file": "/opt/nexus-open-swe-runtime/cli.py",
                "module_sha256": "a" * 64,
                "deepagents_version": "0.7.6",
            },
            "authority_boundary": "execution_runtime_only",
            "process_started": False,
            "outcome_unknown": False,
            "retry_safe": True,
        }
    response = json.dumps(
        {
            "schema": "external_intelligence_worker_result.v1",
            "task_id": "task-1",
            "unit_id": "u1",
            "status": response_status,
            "summary": "bounded result",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    result = {
        "schema": module.PROTOCOL_RESULT_SCHEMA,
        "kind": "worker",
        "operation_id": payload["operation_id"],
        "status": "COMPLETED",
        "session_id": "ses_open_swe_1234567890abcdef1234",
        "response_text": response,
        "provider_id": "google_genai",
        "model_id": "gemini-test",
        "directory": payload["workspace_path"],
        "version": "0.7.6",
        "stdout_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "export_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "process_started": True,
        "outcome_unknown": False,
        "retry_safe": False,
        "diagnosis_status": "ROOT_CAUSE_SUPPORTED",
        "diagnosis_sha256": "d" * 64,
        "diagnosis_evidence_paths": ["a.py"],
        "repair_admitted": response_status == "IMPLEMENTATION_COMPLETED",
        "repair_phase_count": 1 if response_status == "IMPLEMENTATION_COMPLETED" else 0,
        "worker_identity_sha256": payload["worker_identity_sha256"],
    }
    if isinstance(payload.get("effect_authorization"), dict):
        authorization = payload["effect_authorization"]
        projection = payload["tool_projection_manifest"]
        phase_surfaces = {
            "diagnosis": ["read_file", "record_diagnosis"],
            "repair": ["read_file", "record_worker_result", "write_file"],
        }
        receipt_material = {
            "schema": module.EXPOSURE_RECEIPT_SCHEMA,
            "operation_id": payload["operation_id"],
            "attempt_id": authorization["attempt_id"],
            "provider": payload["provider_id"],
            "backend_id": projection["backend_id"],
            "authorization_hash": authorization["authorization_hash"],
            "projection_hash": projection["projection_hash"],
            "actual_exposed_tools": [
                "read_file",
                "record_diagnosis",
                "record_worker_result",
                "write_file",
            ],
            "phase_tool_surfaces": phase_surfaces,
            "authority_kind": "DERIVED_EXPOSURE_EVIDENCE_ONLY",
        }
        result.update(
            effect_authorization_hash=authorization["authorization_hash"],
            tool_projection_hash=projection["projection_hash"],
            execution_exposure_receipt={
                **receipt_material,
                "exposure_hash": _hash_json(receipt_material),
            },
        )
    return result


def test_worker_external_protocol_maps_completed_result(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
    ).bind_worker(_worker())

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert isinstance(result, OpenCodeRunResult)
    assert result.status == "COMPLETED"
    assert result.worker_backend == "open_swe"
    assert result.provider_id == "google_genai"
    assert result.model_id == "gemini-test"
    assert result.diagnosis_status == "ROOT_CAUSE_SUPPORTED"
    assert result.repair_admitted is True
    assert calls[0]["operation"] == "identity"
    assert calls[1]["operation"] == "worker_run"
    assert calls[1]["worker_identity"] == _worker()


def test_wave4_effect_pair_is_forwarded_and_exposure_receipt_is_read_back(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
    ).bind_worker(_worker())
    operation_id = transport.prepare_operation_id(
        "worker_run",
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        session_id="",
    )
    authorization, projection = _projected_pair(operation_id)

    result = transport.run_new(
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        operation_id=operation_id,
        effect_authorization=authorization,
        tool_projection_manifest=projection,
    )

    assert result.status == "COMPLETED"
    assert calls[1]["attempt_id"] == authorization["attempt_id"]
    assert calls[1]["effect_authorization"] == authorization
    assert calls[1]["tool_projection_manifest"] == projection
    assert result.effect_authorization_hash == authorization["authorization_hash"]
    assert result.tool_projection_hash == projection["projection_hash"]
    exposure_receipt = result.execution_exposure_receipt
    assert isinstance(exposure_receipt, dict)
    assert exposure_receipt["schema"] == module.EXPOSURE_RECEIPT_SCHEMA
    assert exposure_receipt["projection_hash"] == projection["projection_hash"]


def test_wave4_tampered_exposure_receipt_never_returns_success(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        result = _completed(module, payload)
        if payload["operation"] == "worker_run":
            result["execution_exposure_receipt"]["actual_exposed_tools"].append("shell")
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    operation_id = transport.prepare_operation_id(
        "worker_run",
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        session_id="",
    )
    authorization, projection = _projected_pair(operation_id)

    result = transport.run_new(
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        operation_id=operation_id,
        effect_authorization=authorization,
        tool_projection_manifest=projection,
    )

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.error == "OPEN_SWE_EXPOSURE_RECEIPT_TOOLS_INVALID"


def test_wave4_effect_bound_reconcile_reuses_same_projection_identity(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    operation_id = transport.prepare_operation_id(
        "worker_run",
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        session_id="",
    )
    authorization, projection = _projected_pair(operation_id)

    first = transport.run_new(
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        operation_id=operation_id,
        effect_authorization=authorization,
        tool_projection_manifest=projection,
    )
    reconciled = transport.reconcile_workspace(
        workspace_path=str(workspace),
        operation_id=operation_id,
        effect_authorization=authorization,
        tool_projection_manifest=projection,
    )

    assert first.status == reconciled.status == "COMPLETED"
    assert calls[-1]["operation"] == "worker_reconcile"
    assert calls[-1]["effect_authorization"] == authorization
    assert calls[-1]["tool_projection_manifest"] == projection
    reconciled_receipt = reconciled.execution_exposure_receipt
    assert isinstance(reconciled_receipt, dict)
    assert reconciled_receipt["projection_hash"] == projection["projection_hash"]


def test_worker_result_must_bind_to_requested_operation_id(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        result = _completed(module, payload)
        if payload["operation"] == "worker_run":
            result["operation_id"] = "foreign-operation"
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.error == "OPERATION_ID_MISMATCH"


def test_reconcile_requires_original_operation_id_and_reuses_it(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        result = _completed(module, payload)
        if payload["operation"] == "worker_run":
            result["operation_id"] = payload["operation_id"]
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    first = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    reconciled = transport.reconcile_workspace(
        workspace_path=str(workspace), operation_id=first.operation_id
    )

    assert reconciled.operation_id == first.operation_id
    assert calls[-1]["operation"] == "worker_reconcile"
    assert calls[-1]["operation_id"] == first.operation_id


def test_prepared_operation_id_rejects_artifact_drift_before_worker_send(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        raise AssertionError("worker dispatch must be rejected before send")

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    prepared = transport.prepare_operation_id(
        "worker_run",
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        session_id="",
    )
    artifact.write_text('{"failure":"changed"}\n', encoding="utf-8")
    result = transport.run_new(
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
        operation_id=prepared,
    )
    assert result.error == "OPERATION_ID_MISMATCH"
    assert calls == ["identity"]


@pytest.mark.parametrize("malformed", [None, False, 0, "bad"])
def test_malformed_supplied_operation_id_rejected_before_identity_probe(
    tmp_path, monkeypatch, malformed
):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []
    monkeypatch.setattr(module, "_runtime_call", lambda *args, **kwargs: calls.append(args))
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    with pytest.raises(FanoutError, match="OPERATION_ID_REQUIRED"):
        transport.run_new(
            prompt=_prompt(),
            artifact_path=str(artifact),
            workspace_path=str(workspace),
            operation_id=malformed,
        )
    assert calls == []


def test_worker_timeout_is_unknown_and_reconcile_is_distinct_read_only_call(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    operations = []

    def runtime_call(_executable, payload, **_kwargs):
        operations.append(payload["operation"])
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        if payload["operation"] == "worker_run":
            return None, "", True, "runtime_timeout"
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "worker",
                "status": "OPEN_SWE_OUTCOME_UNKNOWN",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
                "directory": payload["workspace_path"],
                "process_started": False,
                "outcome_unknown": True,
                "retry_safe": False,
                "worker_identity_sha256": payload["worker_identity_sha256"],
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    ).bind_worker(_worker())

    first = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    reconciled = transport.reconcile_workspace(
        workspace_path=str(workspace),
        operation_id=transport.prepare_operation_id(
            "worker_run",
            prompt=_prompt(),
            artifact_path=str(artifact),
            workspace_path=str(workspace),
            session_id="",
        ),
    )

    assert first.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first.outcome_unknown is True
    assert first.retry_safe is False
    assert reconciled.outcome_unknown is True
    assert operations == ["identity", "worker_run", "identity", "worker_reconcile"]


def test_continue_session_binds_exact_session(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    seen = []

    def runtime_call(_executable, payload, **_kwargs):
        seen.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    session = "ses_open_swe_1234567890abcdef1234"
    result = transport.continue_session(
        session_id=session,
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
    )
    assert result.status == "COMPLETED"
    assert seen[0]["operation"] == "identity"
    assert seen[1]["operation"] == "worker_continue"
    assert seen[1]["session_id"] == session
    with pytest.raises(Exception, match="INVALID_SESSION_ID"):
        transport.continue_session(
            session_id="bad",
            prompt=_prompt(),
            artifact_path=str(artifact),
            workspace_path=str(workspace),
        )


def test_invalid_session_is_rejected_before_identity_probe(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []
    monkeypatch.setattr(module, "_runtime_call", lambda *args, **kwargs: calls.append(args))
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    with pytest.raises(Exception, match="INVALID_SESSION_ID"):
        transport.continue_session(
            session_id="invalid",
            prompt=_prompt(),
            artifact_path=str(artifact),
            workspace_path=str(workspace),
        )
    assert calls == []


def test_full_worker_identity_is_bound_and_substitution_is_rejected():
    from nexus.services.open_swe_external_intelligence import OpenSWEWorkerTransport

    worker = _worker()
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
    )
    assert transport.bind_worker(worker) is transport
    with pytest.raises(Exception, match="WORKER_IDENTITY_SUBSTITUTION_FORBIDDEN"):
        transport.bind_worker({**worker, "worker_id": "google/gemini-worker-b"})


def test_worker_attestation_mismatch_fails_closed(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        result = _completed(module, payload)
        result["model_id"] = "substituted"
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    ).bind_worker(_worker())
    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.error == "MODEL_ATTESTATION_MISMATCH"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def _repo_and_envelope(tmp_path: Path) -> tuple[Path, str, Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "nexus-test@example.invalid")
    _git(repo, "config", "user.name", "Nexus Test")
    (repo / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    payload = {
        "schema": "external_execution_envelope.v1",
        "binding": {
            "repository": "example/repo",
            "item_type": "task",
            "item_id": "task-1",
            "revision": "rev-1",
            "main_sha": base,
            "task_card_ref": "tasks/example.md",
            "task_card_hash": "b" * 64,
            "context_pack_sha256": "c" * 64,
        },
        "goal": "repair a.py",
        "root_cause": "VALUE must be 2",
        "scope_signal": {
            "production_edit_paths": ["a.py"],
            "required_test_edit_paths": [],
            "conditional_migration_paths": [],
            "read_only_authorities": [],
            "verification_only_paths": [],
            "forbidden_paths": [],
            "max_files": 1,
            "scope_confidence": "HIGH",
            "scope_block_conditions": ["scope expands"],
        },
        "implementation_signal": {
            "inspect_first": ["a.py"],
            "proven_facts": ["base bound"],
            "required_semantics": ["VALUE becomes 2"],
            "suggested_direction": ["minimal edit"],
            "forbidden_behavior": ["scope widening"],
        },
        "verification_signal": {
            "red_probe": "python -m pytest",
            "positive_probes": [],
            "hostile_negative_probes": [],
            "impact_suites": [],
            "static_checks": ["git diff --check"],
            "false_green_conditions": ["empty diff"],
        },
        "worker_binding": {
            "assigned_thread": "UNASSIGNED",
            "persistent_thread": True,
            "create_subagent": False,
            "fallback_allowed": False,
        },
        "model_adaptation": {
            "role_contract": ["bounded"],
            "task_local_invariants": ["a.py only"],
            "known_failure_guards": ["no widening"],
            "execution_strategy": ["minimal"],
            "forbidden_inferences": ["authority"],
            "repair_policy": ["one repair"],
        },
        "stop_conditions": ["scope expands"],
    }
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return repo, base, envelope, hashlib.sha256(canonical.encode()).hexdigest()


def test_fanout_captures_external_open_swe_candidate_and_stops_before_acceptance(
    tmp_path, monkeypatch
):
    import nexus.services.open_swe_external_intelligence as module

    repo, base, envelope, envelope_sha = _repo_and_envelope(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        workspace = Path(payload["workspace_path"])
        (workspace / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=transport,
    )
    result = runtime.run(
        [
            {
                "task_id": "task-1",
                "unit_id": "u1",
                "envelope_ref": str(envelope),
                "envelope_sha256": envelope_sha,
                "expected_base_sha": base,
                "mutation_paths": ["a.py"],
                "provider": "google_genai",
                "model": "google_genai/gemini-test",
                "selected_worker": _worker(),
            }
        ],
        CapacityLease(1, 1, 1, 1),
    )

    assert result["errors"] == {}
    receipt = result["receipts"]["u1"]
    assert receipt["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert receipt["changed_paths"] == ["a.py"]
    assert receipt["worker_backend"] == "open_swe"
    assert receipt["diagnosis_status"] == "ROOT_CAUSE_SUPPORTED"
    assert receipt["claim_ceiling"] == "CANDIDATE_READY_FOR_VERIFICATION"
    stripped = dict(receipt)
    for field in (
        "diagnosis_status",
        "diagnosis_sha256",
        "diagnosis_evidence_paths",
        "repair_admitted",
        "repair_phase_count",
        "worker_identity_sha256",
    ):
        stripped.pop(field)
    stripped.pop("receipt_id")
    stripped["receipt_id"] = hashlib.sha256(
        json.dumps(stripped, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(ClosureError, match="OPEN_SWE_DIAGNOSIS_RECEIPT_INVALID"):
        validate_worker_receipt(stripped)


# Exact-base lineage witnesses for worker behavior that moved into the external
# runtime. These execute the runtime owner directly with injected fake graphs,
# so the historical node IDs keep real behavioral oracles rather than aliases.
def _external_runtime_module():
    path = Path("runtimes/open_swe/nexus_open_swe_runtime/cli.py").resolve()
    spec = importlib.util.spec_from_file_location("nexus_open_swe_runtime_compat_worker", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RuntimeGraph:
    def __init__(self, surface, *, output=None, effect=None, error=None):
        self.surface = tuple(surface)
        self.output = output
        self.effect = effect
        self.error = error
        self.calls = 0

    def get_graph(self):
        tools = {name: object() for name in self.surface}
        data = SimpleNamespace(tools_by_name=tools)
        return SimpleNamespace(nodes={"tools": SimpleNamespace(data=data)})

    def invoke(self, _payload, config=None):
        self.calls += 1
        assert config in ({"recursion_limit": 40}, {"recursion_limit": 60})
        if self.error is not None:
            raise self.error
        if self.effect is not None:
            self.effect()
        return self.output


def _runtime_record(name: str, envelope: dict):
    return {
        "messages": [SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": envelope}}])]
    }


def _runtime_loader():
    return {"human_message": lambda content: content}


def _runtime_worker_request(tmp_path: Path) -> dict:
    workspace, artifact = _artifact_and_workspace(tmp_path)
    return {
        "operation_id": "b" * 64,
        "provider_id": "google_genai",
        "model_id": "gemini-test",
        "runtime_state_root": str(tmp_path / "runtime-state"),
        "workspace_path": str(workspace),
        "artifact_path": str(artifact),
        "prompt": _prompt(),
        "session_id": "",
        "worker_identity_sha256": "c" * 64,
    }


def test_supported_root_cause_admits_one_bounded_candidate_repair(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    workspace = Path(request["workspace_path"])
    diagnosis = _RuntimeGraph(
        runtime.DIAGNOSIS_TOOLS,
        output=_runtime_record(
            "record_diagnosis",
            {
                "status": "ROOT_CAUSE_SUPPORTED",
                "summary": "a.py contains the failing value",
                "evidence_paths": ["a.py"],
            },
        ),
    )
    repair = _RuntimeGraph(
        runtime.REPAIR_TOOLS,
        output=_runtime_record("record_worker_result", {"summary": "repaired a.py"}),
        effect=lambda: (workspace / "a.py").write_text("VALUE = 2\n", encoding="utf-8"),
    )

    result = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert result["status"] == "COMPLETED"
    assert result["diagnosis_status"] == "ROOT_CAUSE_SUPPORTED"
    assert result["repair_admitted"] is True
    assert result["repair_phase_count"] == 1
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert diagnosis.calls == 1
    assert repair.calls == 1


def test_inconclusive_diagnosis_blocks_without_invoking_repair(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    workspace = Path(request["workspace_path"])
    diagnosis = _RuntimeGraph(
        runtime.DIAGNOSIS_TOOLS,
        output=_runtime_record(
            "record_diagnosis",
            {"status": "INCONCLUSIVE", "summary": "insufficient evidence", "evidence_paths": []},
        ),
    )
    repair = _RuntimeGraph(
        runtime.REPAIR_TOOLS,
        output=_runtime_record("record_worker_result", {"summary": "must not run"}),
    )

    result = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert result["status"] == "COMPLETED"
    assert result["diagnosis_status"] == "INCONCLUSIVE"
    assert result["repair_admitted"] is False
    assert result["repair_phase_count"] == 0
    assert json.loads(result["response_text"])["status"] == "BLOCKED"
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert diagnosis.calls == 1
    assert repair.calls == 0


def test_supported_diagnosis_without_physical_evidence_path_fails_closed(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    workspace = Path(request["workspace_path"])
    diagnosis = _RuntimeGraph(
        runtime.DIAGNOSIS_TOOLS,
        output=_runtime_record(
            "record_diagnosis",
            {"status": "ROOT_CAUSE_SUPPORTED", "summary": "unsupported", "evidence_paths": []},
        ),
    )
    repair = _RuntimeGraph(runtime.REPAIR_TOOLS, output={})

    result = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["outcome_unknown"] is True
    assert result["error"] == "RuntimeErrorBounded"
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert diagnosis.calls == 1
    assert repair.calls == 0


def test_duplicate_diagnosis_records_fail_closed_without_repair(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    workspace = Path(request["workspace_path"])
    duplicate = {
        "messages": [
            SimpleNamespace(
                tool_calls=[
                    {
                        "name": "record_diagnosis",
                        "args": {
                            "envelope": {
                                "status": "ROOT_CAUSE_SUPPORTED",
                                "summary": "one",
                                "evidence_paths": ["a.py"],
                            }
                        },
                    },
                    {
                        "name": "record_diagnosis",
                        "args": {
                            "envelope": {
                                "status": "ROOT_CAUSE_SUPPORTED",
                                "summary": "two",
                                "evidence_paths": ["a.py"],
                            }
                        },
                    },
                ]
            )
        ]
    }
    diagnosis = _RuntimeGraph(runtime.DIAGNOSIS_TOOLS, output=duplicate)
    repair = _RuntimeGraph(runtime.REPAIR_TOOLS, output={})

    result = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["outcome_unknown"] is True
    assert result["error"] == "RuntimeErrorBounded"
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert diagnosis.calls == 1
    assert repair.calls == 0


def test_ambiguous_repair_outcome_reconciles_without_blind_redispatch(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    diagnosis = _RuntimeGraph(
        runtime.DIAGNOSIS_TOOLS,
        output=_runtime_record(
            "record_diagnosis",
            {
                "status": "ROOT_CAUSE_SUPPORTED",
                "summary": "supported",
                "evidence_paths": ["a.py"],
            },
        ),
    )
    repair = _RuntimeGraph(runtime.REPAIR_TOOLS, error=TimeoutError("ambiguous"))

    first = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )
    replay = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert first["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first["outcome_unknown"] is True
    assert replay == first
    assert diagnosis.calls == 1
    assert repair.calls == 1


def test_worker_transport_rejects_forbidden_graph_tool_surface(tmp_path):
    runtime = _external_runtime_module()
    request = _runtime_worker_request(tmp_path)
    diagnosis = _RuntimeGraph(
        set(runtime.DIAGNOSIS_TOOLS) | {"execute"},
        output=_runtime_record(
            "record_diagnosis",
            {"status": "INCONCLUSIVE", "summary": "blocked", "evidence_paths": []},
        ),
    )
    repair = _RuntimeGraph(runtime.REPAIR_TOOLS, output={})

    result = runtime._worker_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        diagnosis_factory=lambda *_args: diagnosis,
        repair_factory=lambda *_args: repair,
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["outcome_unknown"] is True
    assert result["error"] == "RuntimeErrorBounded"
    assert diagnosis.calls == 0
    assert repair.calls == 0


def test_fanout_captures_open_swe_candidate_and_stops_before_acceptance(tmp_path, monkeypatch):
    test_fanout_captures_external_open_swe_candidate_and_stops_before_acceptance(
        tmp_path, monkeypatch
    )


def test_real_deepagents_worker_graphs_have_exact_physical_surfaces(tmp_path):
    pytest.importorskip("deepagents")
    runtime = _external_runtime_module()
    assert runtime.DIAGNOSIS_TOOLS == frozenset({
        "glob",
        "grep",
        "ls",
        "read_file",
        "record_diagnosis",
    })
    assert runtime.REPAIR_TOOLS == frozenset({
        "edit_file",
        "glob",
        "grep",
        "ls",
        "read_file",
        "record_worker_result",
        "write_file",
    })


# ---------------------------------------------------------------------------
# Core repository_mutation_binding wiring (bound Open SWE dispatch)
# ---------------------------------------------------------------------------


def _bound_runtime(tmp_path: Path, monkeypatch, *, core_status="BOUND", core_hashes=None):
    import nexus.services.open_swe_external_intelligence as module
    from tests.services.test_external_intelligence_core_binding import (
        TARGET,
        bound_unit_mapping,
        make_bound_repo,
    )

    scenario = make_bound_repo(tmp_path)
    unit = bound_unit_mapping(tmp_path, scenario)
    calls: list[dict] = []

    def runtime_call(_executable, payload, **_kwargs):
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        calls.append(json.loads(json.dumps(payload)))
        if payload["operation"] == "worker_run":
            (Path(payload["workspace_path"]) / TARGET).parent.mkdir(parents=True, exist_ok=True)
            (Path(payload["workspace_path"]) / TARGET).write_text(
                "def test_bound():\n    assert True\n", encoding="utf-8"
            )
        result = _completed(module, payload)
        supplied = (payload.get("core_binding_hash"), payload.get("acceptance_contract_hash"))
        returned = core_hashes or supplied
        result.update(
            core_binding_status=core_status,
            core_binding_hash=returned[0],
            acceptance_contract_hash=returned[1],
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
    )
    return SimpleNamespace(
        scenario=scenario, unit=unit, calls=calls, runtime=runtime, store=store, module=module
    )


def test_bound_dispatch_mints_core_binding_without_changing_semantic_identity(
    tmp_path, monkeypatch
):
    from nexus.services.external_intelligence_core_binding import (
        envelope_canonical_json,
        parse_bound_execution_envelope_v2,
    )
    from nexus.services.external_intelligence_fanout import ExecutionUnit

    ctx = _bound_runtime(tmp_path, monkeypatch)
    semantic_path = Path(ctx.unit["envelope_ref"])
    semantic_bytes = semantic_path.read_bytes()
    unbound_identity = ExecutionUnit.from_mapping({
        key: value for key, value in ctx.unit.items() if key != "core_authority"
    }).identity_sha256

    result = ctx.runtime.run([ctx.unit], CapacityLease(1, 1, 1, 1))

    assert result["errors"] == {}
    receipt = result["receipts"]["u1"]
    assert semantic_path.read_bytes() == semantic_bytes
    assert ExecutionUnit.from_mapping(ctx.unit).identity_sha256 == unbound_identity
    assert receipt["envelope_sha256"] == ctx.unit["envelope_sha256"]
    assert receipt["envelope_ref"] == ctx.unit["envelope_ref"]

    run = next(call for call in ctx.calls if call["operation"] == "worker_run")
    bound_path = Path(run["artifact_path"])
    assert bound_path.parent == ctx.store.bound_envelopes
    assert bound_path.name == f"task-1--u1--{receipt['attempt_id']}.json"
    _semantic, binding, bound_sha = parse_bound_execution_envelope_v2(
        bound_path.read_text(encoding="utf-8"),
        semantic_envelope_sha256=ctx.unit["envelope_sha256"],
    )
    bound = json.loads(bound_path.read_text(encoding="utf-8"))
    assert bound_sha == hashlib.sha256(envelope_canonical_json(bound).encode()).hexdigest()
    prompt_fields = dict(line.split("=", 1) for line in run["prompt"].splitlines() if "=" in line)
    assert prompt_fields["envelope_sha256"] == bound_sha
    assert prompt_fields["semantic_envelope_sha256"] == ctx.unit["envelope_sha256"]
    assert binding["operation_id"] == run["operation_id"] == receipt["operation_id"]
    assert binding["attempt_id"] == run["attempt_id"] == receipt["attempt_id"]
    assert run["core_binding_hash"] == binding["binding_hash"]
    assert run["acceptance_contract_hash"] == binding["core"]["acceptance_contract_hash"]
    assert receipt["bound_envelope_ref"] == str(bound_path)
    assert receipt["bound_envelope_sha256"] == bound_sha
    assert receipt["core_binding_status"] == "BOUND"
    assert receipt["core_binding_hash"] == binding["binding_hash"]
    assert receipt["acceptance_contract_hash"] == binding["core"]["acceptance_contract_hash"]
    attempt = json.loads(
        (ctx.store.attempts / "task-1--u1--initial.json").read_text(encoding="utf-8")
    )
    assert attempt["bound_envelope_sha256"] == bound_sha
    assert attempt["core_binding_hash"] == binding["binding_hash"]
    assert attempt["envelope_sha256"] == ctx.unit["envelope_sha256"]
    assert Path(attempt["capability_discovery_receipt_ref"]).is_file()
    assert validate_worker_receipt(receipt)["core_binding_status"] == "BOUND"


def test_bound_operation_id_is_binding_free_and_material_checked(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module
    from nexus.services.external_intelligence_core_binding import bound_operation_material

    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    ).bind_worker(_worker())
    material = bound_operation_material(
        operation="worker_run",
        workspace_path=tmp_path,
        attempt_id="attempt-1",
        unit_identity_sha256="1" * 64,
        semantic_envelope_sha256="2" * 64,
        worker_identity_sha256=transport.worker_identity_sha256,
    )
    operation_id = transport.prepare_operation_id(
        "worker_run",
        prompt="any prompt",
        artifact_path="",
        workspace_path=str(tmp_path),
        session_id="",
        operation_material=material,
    )
    assert operation_id == _hash_json(material)
    # Prompt/artifact bytes (which embed the binding) do not feed the bound id.
    assert operation_id == transport.prepare_operation_id(
        "worker_run",
        prompt="different prompt",
        artifact_path="",
        workspace_path=str(tmp_path),
        session_id="",
        operation_material=material,
    )
    with pytest.raises(FanoutError, match="OPERATION_MATERIAL_INVALID"):
        transport.prepare_operation_id(
            "worker_run",
            prompt="",
            artifact_path="",
            workspace_path=str(tmp_path),
            session_id="",
            operation_material={**material, "worker_identity_sha256": "0" * 64},
        )


def test_bound_reconcile_payload_carries_core_hashes(tmp_path, monkeypatch):
    ctx = _bound_runtime(tmp_path, monkeypatch)
    from nexus.services.external_intelligence_fanout import ExecutionUnit

    unit = ExecutionUnit.from_mapping(ctx.unit)
    original_finalize = ctx.runtime._finalize_initial

    def crash_after_dispatch(*args, **kwargs):
        raise RuntimeError("controller crashed after worker returned")

    ctx.runtime._finalize_initial = crash_after_dispatch
    first = ctx.runtime.run([ctx.unit], CapacityLease(1, 1, 1, 1))
    assert "u1" in first["errors"]
    attempt = ctx.store.existing_initial_attempt(unit)
    assert attempt["state"] == "DISPATCHING"

    ctx.runtime._finalize_initial = original_finalize
    second = ctx.runtime.run([ctx.unit], CapacityLease(1, 1, 1, 1))
    reconcile = [call for call in ctx.calls if call["operation"] == "worker_reconcile"]
    assert len(reconcile) == 1
    assert reconcile[0]["artifact_path"] == ""
    assert reconcile[0]["operation_id"] == attempt["operation_id"]
    assert reconcile[0]["core_binding_hash"] == attempt["core_binding_hash"]
    assert reconcile[0]["acceptance_contract_hash"] == attempt["acceptance_contract_hash"]
    assert second["errors"] == {}
    assert second["receipts"]["u1"]["core_binding_status"] == "BOUND"


@pytest.mark.parametrize(
    ("core_status", "core_hashes"),
    [
        ("LEGACY_UNBOUND", ("", "")),
        ("BOUND", ("sha256:" + "9" * 64, "sha256:" + "8" * 64)),
    ],
)
def test_bound_dispatch_requires_runtime_bound_attestation(
    tmp_path, monkeypatch, core_status, core_hashes
):
    from nexus.services.external_intelligence_fanout import ExecutionUnit

    ctx = _bound_runtime(tmp_path, monkeypatch, core_status=core_status, core_hashes=core_hashes)
    result = ctx.runtime.run([ctx.unit], CapacityLease(1, 1, 1, 1))
    assert result["errors"] == {"u1": "FANOUT_RECONCILIATION_REQUIRED"}
    attempt = ctx.store.existing_initial_attempt(ExecutionUnit.from_mapping(ctx.unit))
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["transport_status"] == "OPEN_SWE_OUTCOME_UNKNOWN"


def test_transport_maps_core_attestation_mismatch_to_outcome_unknown(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        result = _completed(module, payload)
        if payload["operation"] != "identity":
            result.update(core_binding_status="LEGACY_UNBOUND")
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    ).bind_worker(_worker())
    result = transport.reconcile_workspace(
        workspace_path=str(workspace),
        operation_id="c" * 64,
        core_binding={
            "core_binding_hash": "sha256:" + "1" * 64,
            "acceptance_contract_hash": "sha256:" + "2" * 64,
        },
    )
    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.error == "CORE_BINDING_ATTESTATION_MISMATCH"


def test_bound_dispatch_revalidation_failure_blocks_before_effect(tmp_path, monkeypatch):
    from nexus.services.external_intelligence_fanout import ExecutionUnit

    ctx = _bound_runtime(tmp_path, monkeypatch)
    original_mark = ctx.store.mark_dispatching

    def dirty_after_mark(attempt, **kwargs):
        value = original_mark(attempt, **kwargs)
        (Path(value["workspace_path"]) / "stray.txt").write_text("x", encoding="utf-8")
        return value

    ctx.store.mark_dispatching = dirty_after_mark
    result = ctx.runtime.run([ctx.unit], CapacityLease(1, 1, 1, 1))
    assert result["errors"] == {"u1": "CORE_BINDING_REVALIDATION_FAILED:workspace_dirty"}
    assert [call for call in ctx.calls if call["operation"] == "worker_run"] == []
    attempt = ctx.store.existing_initial_attempt(ExecutionUnit.from_mapping(ctx.unit))
    assert attempt["state"] == "FAILED"


def test_bound_dispatch_without_execution_lane_fails_before_attempt(tmp_path, monkeypatch):
    from tests.services.test_external_intelligence_core_binding import (
        authority_inputs,
        bound_unit_mapping,
        bound_worker,
    )

    ctx = _bound_runtime(tmp_path, monkeypatch)
    inputs = authority_inputs(ctx.scenario.base, ctx.scenario.card_hash, bound_worker(), lane="")
    unit = bound_unit_mapping(tmp_path / "laneless", ctx.scenario, authority=inputs)
    result = ctx.runtime.run([unit], CapacityLease(1, 1, 1, 1))
    assert result["errors"] == {"u1": "CORE_EXECUTION_LANE_REQUIRED"}
    assert ctx.calls == []
    assert not (ctx.store.attempts / "task-1--u1--initial.json").exists()

    unit_without_authority = {k: v for k, v in unit.items() if k != "core_authority"}
    result = ctx.runtime.run([unit_without_authority], CapacityLease(1, 1, 1, 1))
    assert result["errors"] == {"u1": "CORE_BINDING_AUTHORITY_REQUIRED"}
    assert ctx.calls == []


# --- #2188: observed-model pin for opencli_chatgpt ---------------------------

_OBSERVED = "gpt-5-6-thinking"
_OPENCLI_BINDING = {
    "executable": "/opt/opencli",
    "profile": "profile-a",
    "site_session": "persistent",
    "timeout_seconds": 240,
}


def _opencli_worker():
    return {
        **_worker(),
        "worker_id": "opencli/chatgpt-worker-a",
        "provider": "opencli_chatgpt",
        "model": "opencli_chatgpt/very-high",
    }


def _invocation_receipt(operation_id, *, revision=_OBSERVED, provider_revision=_OBSERVED):
    return {
        "operation_id": operation_id,
        "provider_id": "opencli_chatgpt",
        "model_id": "very-high",
        "provider_model_revision": provider_revision,
        "backend_identity": {
            "configured_identity": {"provider_id": "opencli_chatgpt", "model_id": "very-high"},
            "observed_execution_identity": {
                "provider_id": "opencli_chatgpt",
                "model_id": revision,
                "model_revision": revision,
                "observation_source": "opencli_ask_reply",
            },
        },
    }


def _opencli_transport(module):
    return module.OpenSWEWorkerTransport(
        model_provider="opencli_chatgpt",
        model_id="very-high",
        expected_observed_model=_OBSERVED,
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
        transport_config=_OPENCLI_BINDING,
    ).bind_worker(_opencli_worker())


def _run_opencli_worker(tmp_path, monkeypatch, receipts):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        result = _completed(module, payload)
        if payload["operation"] != "identity":
            result.update(provider_id="opencli_chatgpt", model_id="very-high")
            made = receipts(payload["operation_id"])
            if made is not None:
                result["model_invocation_receipts"] = made
        return result, "", payload["operation"] != "identity", ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    return _opencli_transport(module).run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )


def test_opencli_worker_with_expected_observed_model_completes(tmp_path, monkeypatch):
    result = _run_opencli_worker(tmp_path, monkeypatch, lambda op: [_invocation_receipt(op)])
    assert result.status == "COMPLETED"
    assert len(result.model_invocation_receipts) == 1
    assert result.model_invocation_receipts[0]["provider_model_revision"] == _OBSERVED


@pytest.mark.parametrize(
    "receipts",
    [
        pytest.param(lambda op: [_invocation_receipt(op, revision="gpt-6-thinking")], id="wrong"),
        pytest.param(
            lambda op: [_invocation_receipt(op), _invocation_receipt(op, revision="gpt-6")],
            id="one-of-many-wrong",
        ),
        pytest.param(lambda op: None, id="no-receipts"),
        pytest.param(lambda op: [], id="empty-receipts"),
        pytest.param(
            lambda op: [
                _invocation_receipt(op, revision="NOT_MEASURED", provider_revision="NOT_MEASURED")
            ],
            id="not-measured",
        ),
        pytest.param(lambda op: [_invocation_receipt("f" * 64)], id="other-operation"),
        pytest.param(lambda op: ["not-a-mapping"], id="malformed"),
    ],
)
def test_opencli_worker_unproven_observed_model_is_outcome_unknown(tmp_path, monkeypatch, receipts):
    result = _run_opencli_worker(tmp_path, monkeypatch, receipts)
    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.retry_safe is False
    assert result.error == "OBSERVED_MODEL_ATTESTATION_MISMATCH"


def test_opencli_worker_requires_expected_observed_model():
    import nexus.services.open_swe_external_intelligence as module

    with pytest.raises(
        module.OpenSWEExternalIntelligenceError,
        match="OPEN_SWE_EXPECTED_OBSERVED_MODEL_REQUIRED",
    ):
        module.OpenSWEWorkerTransport(
            model_provider="opencli_chatgpt",
            model_id="very-high",
            executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
            expected_artifact_sha256="a" * 64,
            transport_config=_OPENCLI_BINDING,
        )
    with pytest.raises(
        module.OpenSWEExternalIntelligenceError,
        match="OPEN_SWE_EXPECTED_OBSERVED_MODEL_PROVIDER_MISMATCH",
    ):
        module.OpenSWEWorkerTransport(
            model_provider="google_genai",
            model_id="gemini-test",
            expected_observed_model=_OBSERVED,
            executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
            expected_artifact_sha256="a" * 64,
        )


def test_fanout_rejects_completed_result_without_observed_model_proof(tmp_path, monkeypatch):
    # Defense in depth: even if a transport returns COMPLETED, fanout re-checks
    # the pinned observed model against the result's invocation receipts.
    import nexus.services.open_swe_external_intelligence as module

    repo, base, envelope, envelope_sha = _repo_and_envelope(tmp_path)

    def runtime_call(_executable, payload, **_kwargs):
        if payload["operation"] == "identity":
            return _completed(module, payload), "", False, ""
        (Path(payload["workspace_path"]) / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    transport.expected_observed_model = _OBSERVED
    # Simulate a transport whose own check is broken; only fanout's re-check remains.
    monkeypatch.setattr(module, "observed_model_violation", lambda *_a, **_k: False)
    store = FanoutStore(tmp_path / "state")
    runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=store,
        transport=transport,
    )
    result = runtime.run(
        [
            {
                "task_id": "task-1",
                "unit_id": "u1",
                "envelope_ref": str(envelope),
                "envelope_sha256": envelope_sha,
                "expected_base_sha": base,
                "mutation_paths": ["a.py"],
                "provider": "google_genai",
                "model": "google_genai/gemini-test",
                "selected_worker": _worker(),
            }
        ],
        CapacityLease(1, 1, 1, 1),
    )

    assert "u1" not in result["receipts"]
    assert result["errors"] == {"u1": "OBSERVED_MODEL_ATTESTATION_MISMATCH"}
    (attempt_file,) = sorted((tmp_path / "state" / "attempts").rglob("*.json"))
    attempt = json.loads(attempt_file.read_text(encoding="utf-8"))
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["transport_status"] == "OBSERVED_MODEL_ATTESTATION_MISMATCH"
