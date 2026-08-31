from __future__ import annotations

import hashlib
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


class FakeGraph:
    def __init__(self, surface, invoke):
        self.surface = tuple(surface)
        self._invoke = invoke
        self.calls = 0

    def get_graph(self):
        tools = {name: object() for name in self.surface}
        return SimpleNamespace(
            nodes={"tools": SimpleNamespace(data=SimpleNamespace(tools_by_name=tools))}
        )

    def invoke(self, payload, config=None):
        self.calls += 1
        return self._invoke(payload, config)


def _record(name: str, envelope: dict):
    return {
        "messages": [SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": envelope}}])]
    }


def _prompt() -> str:
    return "\n".join([
        "task_id=task-1",
        "unit_id=u1",
        'authorized_mutation_paths=["a.py"]',
        "bounded task",
    ])


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
    import hashlib

    return repo, base, envelope, hashlib.sha256(canonical.encode()).hexdigest()


def _transport(tmp_path: Path, diagnosis: dict, *, repair_error: bool = False):
    from nexus.services.open_swe_external_intelligence import (
        DIAGNOSIS_TOOL_SURFACE,
        REPAIR_TOOL_SURFACE,
        OpenSWEWorkerTransport,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"failure":"VALUE must be 2"}\n', encoding="utf-8")

    diagnosis_graph = FakeGraph(
        DIAGNOSIS_TOOL_SURFACE,
        lambda _payload, _config: _record("record_diagnosis", diagnosis),
    )

    def repair_invoke(_payload, _config):
        if repair_error:
            raise TimeoutError("ambiguous provider outcome")
        (workspace / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
        return _record("record_worker_result", {"summary": "repaired a.py"})

    repair_graph = FakeGraph(REPAIR_TOOL_SURFACE, repair_invoke)
    graphs = {"diagnosis": diagnosis_graph, "repair": repair_graph}
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        model_factory=lambda _provider, _model: object(),
        graph_factory=lambda phase, _model, _root, _paths: graphs[phase],
        message_factory=lambda content: content,
    )
    return transport, workspace, artifact, diagnosis_graph, repair_graph


def test_supported_root_cause_admits_one_bounded_candidate_repair(tmp_path):
    transport, workspace, artifact, diagnosis_graph, repair_graph = _transport(
        tmp_path,
        {
            "status": "ROOT_CAUSE_SUPPORTED",
            "summary": "a.py retains the failing value",
            "evidence_paths": ["a.py"],
        },
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert isinstance(result, OpenCodeRunResult)
    assert result.status == "COMPLETED"
    assert result.provider_id == "google_genai"
    assert result.model_id == "gemini-test"
    assert result.session_id.startswith("ses_open_swe_")
    assert json.loads(result.response_text) == {
        "schema": "external_intelligence_worker_result.v1",
        "task_id": "task-1",
        "unit_id": "u1",
        "status": "IMPLEMENTATION_COMPLETED",
        "summary": "repaired a.py",
    }
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert diagnosis_graph.calls == 1
    assert repair_graph.calls == 1


def test_inconclusive_diagnosis_blocks_without_invoking_repair(tmp_path):
    transport, workspace, artifact, diagnosis_graph, repair_graph = _transport(
        tmp_path,
        {"status": "INCONCLUSIVE", "summary": "insufficient evidence", "evidence_paths": []},
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert result.status == "COMPLETED"
    assert json.loads(result.response_text)["status"] == "BLOCKED"
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert diagnosis_graph.calls == 1
    assert repair_graph.calls == 0


def test_supported_diagnosis_without_physical_evidence_path_fails_closed(tmp_path):
    transport, workspace, artifact, diagnosis_graph, repair_graph = _transport(
        tmp_path,
        {"status": "ROOT_CAUSE_SUPPORTED", "summary": "unsupported", "evidence_paths": []},
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.error == "ValueError"
    assert diagnosis_graph.calls == 1
    assert repair_graph.calls == 0
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_duplicate_diagnosis_records_fail_closed_without_repair(tmp_path):
    from nexus.services.open_swe_external_intelligence import (
        DIAGNOSIS_TOOL_SURFACE,
        REPAIR_TOOL_SURFACE,
        OpenSWEWorkerTransport,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}\n", encoding="utf-8")
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
    diagnosis_graph = FakeGraph(DIAGNOSIS_TOOL_SURFACE, lambda *_args: duplicate)
    repair_graph = FakeGraph(REPAIR_TOOL_SURFACE, lambda *_args: {})
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        model_factory=lambda *_args: object(),
        graph_factory=lambda phase, *_args: {
            "diagnosis": diagnosis_graph,
            "repair": repair_graph,
        }[phase],
        message_factory=lambda content: content,
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert repair_graph.calls == 0
    assert (workspace / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_ambiguous_repair_outcome_reconciles_without_blind_redispatch(tmp_path):
    transport, workspace, artifact, diagnosis_graph, repair_graph = _transport(
        tmp_path,
        {
            "status": "ROOT_CAUSE_SUPPORTED",
            "summary": "supported",
            "evidence_paths": ["a.py"],
        },
        repair_error=True,
    )

    first = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    replay = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )
    reconciled = transport.reconcile_workspace(workspace_path=str(workspace))

    assert first.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first.outcome_unknown is True
    assert replay == first
    assert reconciled == first
    assert diagnosis_graph.calls == 1
    assert repair_graph.calls == 1


def test_worker_transport_rejects_forbidden_graph_tool_surface(tmp_path):
    from nexus.services.open_swe_external_intelligence import OpenSWEWorkerTransport

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}\n", encoding="utf-8")
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        model_factory=lambda _provider, _model: object(),
        graph_factory=lambda _phase, _model, _root, _paths: FakeGraph(
            ["read_file", "execute"], lambda *_args: {}
        ),
        message_factory=lambda content: content,
    )

    result = transport.run_new(
        prompt=_prompt(), artifact_path=str(artifact), workspace_path=str(workspace)
    )

    assert result.status == "OPEN_SWE_TOOL_SURFACE_INVALID"
    assert result.process_started is False
    assert result.retry_safe is False


def test_full_worker_identity_is_bound_and_substitution_is_rejected(tmp_path):
    from nexus.services.open_swe_external_intelligence import OpenSWEWorkerTransport

    worker = {
        "worker_id": "google/gemini-worker-a",
        "provider": "google_genai",
        "model": "google_genai/gemini-test",
        "role_ceiling": "bounded repair",
        "admission_evidence_ref": "admission-a",
        "admission_evidence_hash": "a" * 64,
        "selection_evidence_ref": "selection-a",
        "selection_evidence_hash": "b" * 64,
    }
    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        require_worker_binding=True,
    )

    assert transport.bind_worker(worker) is transport
    with pytest.raises(Exception, match="WORKER_IDENTITY_SUBSTITUTION_FORBIDDEN"):
        transport.bind_worker({**worker, "worker_id": "google/gemini-worker-b"})


def test_fanout_captures_open_swe_candidate_and_stops_before_acceptance(tmp_path):
    from nexus.services.open_swe_external_intelligence import (
        DIAGNOSIS_TOOL_SURFACE,
        REPAIR_TOOL_SURFACE,
        OpenSWEWorkerTransport,
    )

    repo, base, envelope, envelope_sha = _repo_and_envelope(tmp_path)

    def graph_factory(phase, _model, workspace, _paths):
        if phase == "diagnosis":
            return FakeGraph(
                DIAGNOSIS_TOOL_SURFACE,
                lambda *_args: _record(
                    "record_diagnosis",
                    {
                        "status": "ROOT_CAUSE_SUPPORTED",
                        "summary": "a.py has VALUE 1",
                        "evidence_paths": ["a.py"],
                    },
                ),
            )

        def repair(*_args):
            (workspace / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
            return _record("record_worker_result", {"summary": "set VALUE to 2"})

        return FakeGraph(REPAIR_TOOL_SURFACE, repair)

    transport = OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        model_factory=lambda *_args: object(),
        graph_factory=graph_factory,
        message_factory=lambda content: content,
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
                "selected_worker": {
                    "worker_id": "google/gemini-worker-a",
                    "provider": "google_genai",
                    "model": "google_genai/gemini-test",
                    "role_ceiling": "bounded repair",
                    "admission_evidence_ref": "admission-a",
                    "admission_evidence_hash": "a" * 64,
                    "selection_evidence_ref": "selection-a",
                    "selection_evidence_hash": "b" * 64,
                },
            }
        ],
        CapacityLease(1, 1, 1, 1),
    )

    assert result["errors"] == {}
    receipt = result["receipts"]["u1"]
    assert receipt["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert receipt["changed_paths"] == ["a.py"]
    assert receipt["provider_id"] == "google_genai"
    assert receipt["model_id"] == "gemini-test"
    assert receipt["candidate_commit"]
    assert receipt["candidate_tree"]
    assert receipt["diagnosis_status"] == "ROOT_CAUSE_SUPPORTED"
    assert receipt["worker_backend"] == "open_swe"
    assert len(receipt["diagnosis_sha256"]) == 64
    assert receipt["diagnosis_evidence_paths"] == ["a.py"]
    assert receipt["repair_admitted"] is True
    assert receipt["repair_phase_count"] == 1
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

    backendless = dict(receipt)
    backendless.pop("worker_backend")
    backendless.pop("receipt_id")
    backendless["receipt_id"] = hashlib.sha256(
        json.dumps(backendless, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(ClosureError, match="WORKER_BACKEND_REQUIRED"):
        validate_worker_receipt(backendless)


def test_real_deepagents_worker_graphs_have_exact_physical_surfaces(tmp_path):
    pytest.importorskip("deepagents")
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from nexus.services.open_swe_external_intelligence import (
        DIAGNOSIS_TOOL_SURFACE,
        REPAIR_TOOL_SURFACE,
        _load_runtime,
        _ScopedRepairBackend,
        build_diagnosis_graph,
        build_repair_graph,
        executable_tool_surface,
    )

    class SurfaceModel(BaseChatModel):
        model_name: str = "surface"

        @property
        def _llm_type(self):
            return "task003-surface"

        def _get_ls_params(self, *args, **kwargs):
            return {"ls_provider": "task003", "ls_model_name": "surface"}

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])

    runtime = _load_runtime()
    model = SurfaceModel()
    diagnosis = build_diagnosis_graph(model, tmp_path, runtime, profile_key="task003:surface")
    repair = build_repair_graph(
        model,
        tmp_path,
        runtime,
        allowed_paths=("a.py",),
        profile_key="task003:surface",
    )

    assert set(executable_tool_surface(diagnosis)) == DIAGNOSIS_TOOL_SURFACE
    assert set(executable_tool_surface(repair)) == REPAIR_TOOL_SURFACE
    assert "execute" not in executable_tool_surface(repair)
    assert "task" not in executable_tool_surface(repair)
    assert "delete_file" not in executable_tool_surface(repair)
    scoped = _ScopedRepairBackend(
        runtime.filesystem_backend(root_dir=tmp_path, virtual_mode=True),
        tmp_path,
        ("a.py",),
    )
    with pytest.raises(PermissionError, match="OPEN_SWE_MUTATION_PATH_FORBIDDEN"):
        scoped.write("/b.py", "forbidden\n")
    assert not (tmp_path / "b.py").exists()
    scoped.write("/a.py", "allowed\n")
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "allowed\n"
