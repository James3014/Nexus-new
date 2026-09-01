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
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeRunResult,
)


def _prompt() -> str:
    return "\n".join(
        ["task_id=task-1", "unit_id=u1", 'authorized_mutation_paths=["a.py"]', "bounded task"]
    )


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


def _completed(module, payload, *, response_status="IMPLEMENTATION_COMPLETED"):
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
    return {
        "schema": module.PROTOCOL_RESULT_SCHEMA,
        "kind": "worker",
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


def test_worker_external_protocol_maps_completed_result(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai", model_id="gemini-test", require_worker_binding=True
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
    assert calls[0]["operation"] == "worker_run"
    assert calls[0]["worker_identity"] == _worker()


def test_worker_timeout_is_unknown_and_reconcile_is_distinct_read_only_call(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    operations = []

    def runtime_call(_executable, payload, **_kwargs):
        operations.append(payload["operation"])
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
        model_provider="google_genai", model_id="gemini-test"
    ).bind_worker(_worker())

    first = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    reconciled = transport.reconcile_workspace(workspace_path=str(workspace))

    assert first.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first.outcome_unknown is True
    assert first.retry_safe is False
    assert reconciled.outcome_unknown is True
    assert operations == ["worker_run", "worker_reconcile"]


def test_continue_session_binds_exact_session(tmp_path, monkeypatch):
    import nexus.services.open_swe_external_intelligence as module

    workspace, artifact = _artifact_and_workspace(tmp_path)
    seen = []

    def runtime_call(_executable, payload, **_kwargs):
        seen.append(dict(payload))
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(model_provider="google_genai", model_id="gemini-test")
    session = "ses_open_swe_1234567890abcdef1234"
    result = transport.continue_session(
        session_id=session,
        prompt=_prompt(),
        artifact_path=str(artifact),
        workspace_path=str(workspace),
    )
    assert result.status == "COMPLETED"
    assert seen[0]["operation"] == "worker_continue"
    assert seen[0]["session_id"] == session
    with pytest.raises(Exception, match="INVALID_SESSION_ID"):
        transport.continue_session(
            session_id="bad", prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
        )


def test_full_worker_identity_is_bound_and_substitution_is_rejected():
    from nexus.services.open_swe_external_intelligence import OpenSWEWorkerTransport

    worker = _worker()
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai", model_id="gemini-test", require_worker_binding=True
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
        model_provider="google_genai", model_id="gemini-test"
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
        workspace = Path(payload["workspace_path"])
        (workspace / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
        return _completed(module, payload), "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai", model_id="gemini-test"
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
    assert runtime.DIAGNOSIS_TOOLS == frozenset(
        {"glob", "grep", "ls", "read_file", "record_diagnosis"}
    )
    assert runtime.REPAIR_TOOLS == frozenset(
        {"edit_file", "glob", "grep", "ls", "read_file", "record_worker_result", "write_file"}
    )
