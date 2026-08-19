from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.external_intelligence_fanout import (
    CLAIM_CEILING,
    MODEL,
    MODEL_ID,
    PROVIDER_ID,
    WORKER_RECEIPT_SCHEMA,
    AdaptiveDeepSeekFanoutRuntime,
    CapacityLease,
    ExecutionUnit,
    FanoutError,
    FanoutStore,
    GitWorktreeAllocator,
    OpenCodeDeepSeekTransport,
    OpenCodeRunResult,
    WorkspaceLease,
    build_worker_bootstrap,
    parse_worker_result,
    plan_fanout,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "nexus-test@example.invalid")
    _git(root, "config", "user.name", "Nexus Test")
    (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "c.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "a.py", "b.py", "nested/c.py")
    _git(root, "commit", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def make_envelope(
    path: Path,
    base_sha: str,
    *,
    allowed: list[str] | None = None,
    forbidden: list[str] | None = None,
    marker: str = "FULL_ENVELOPE_SECRET_MARKER",
) -> str:
    payload = {
        "schema": "external_execution_envelope.v1",
        "binding": {
            "repository": "example/repo",
            "item_type": "task",
            "item_id": "task-1",
            "revision": "rev-1",
            "main_sha": base_sha,
            "task_card_ref": "tasks/example/00-task.md",
            "task_card_hash": "b" * 64,
            "context_pack_sha256": "c" * 64,
        },
        "goal": f"Implement bounded change. {marker}",
        "root_cause": "Bounded implementation required.",
        "scope_signal": {
            "production_edit_paths": allowed or ["a.py", "b.py", "nested"],
            "required_test_edit_paths": [],
            "conditional_migration_paths": [],
            "read_only_authorities": ["AGENTS.md"],
            "verification_only_paths": [],
            "forbidden_paths": forbidden or [],
            "max_files": 20,
            "scope_confidence": "HIGH",
            "scope_block_conditions": ["scope expands"],
        },
        "implementation_signal": {
            "inspect_first": ["a.py"],
            "proven_facts": ["base is bound"],
            "required_semantics": ["bounded edit only"],
            "suggested_direction": ["minimal change"],
            "forbidden_behavior": ["do not widen scope"],
        },
        "verification_signal": {
            "red_probe": "pytest -q",
            "positive_probes": [],
            "hostile_negative_probes": ["reject scope widening"],
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
            "role_contract": ["DeepSeek V4 Flash L2 Task Engineer, bounded single unit"],
            "task_local_invariants": ["bounded edit only"],
            "known_failure_guards": ["no scope widening"],
            "execution_strategy": ["minimal change with task-local judgment"],
            "forbidden_inferences": ["implementation-as-policy", "authority overreach"],
            "repair_policy": ["one evidence-guided same-unit repair", "no blind retry"],
        },
        "stop_conditions": ["scope expands"],
    }
    text = json.dumps(payload, sort_keys=True, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def unit(
    base: str, envelope: Path, envelope_sha: str, unit_id: str, paths: list[str], **updates
) -> dict:
    value = {
        "task_id": "task-1",
        "unit_id": unit_id,
        "envelope_ref": str(envelope),
        "envelope_sha256": envelope_sha,
        "expected_base_sha": base,
        "mutation_paths": paths,
        "dependencies_ready": True,
        "priority": 0,
    }
    value.update(updates)
    return value


def completed_result(
    task_id: str, unit_id: str, session_id: str, workspace_path: str
) -> OpenCodeRunResult:
    return OpenCodeRunResult(
        status="COMPLETED",
        session_id=session_id,
        response_text=json.dumps({
            "schema": "external_intelligence_worker_result.v1",
            "task_id": task_id,
            "unit_id": unit_id,
            "status": "IMPLEMENTATION_COMPLETED",
            "summary": "bounded implementation complete",
        }),
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        directory=str(Path(workspace_path).resolve()),
        version="1.18.18",
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        export_sha256="3" * 64,
        argv_sha256="4" * 64,
        process_started=True,
        retry_safe=False,
    )


class EditingTransport:
    def __init__(self):
        self.lock = threading.Lock()
        self.prompts: dict[str, str] = {}
        self.sessions: dict[str, str] = {}
        self.continued: list[tuple[str, str]] = []

    @staticmethod
    def _field(prompt: str, name: str) -> str:
        prefix = name + "="
        for line in prompt.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        raise AssertionError(f"missing {name}")

    def run_new(self, *, prompt: str, artifact_path: str, workspace_path: str) -> OpenCodeRunResult:
        task_id = self._field(prompt, "task_id")
        unit_id = self._field(prompt, "unit_id")
        session = f"ses_test_{unit_id}_00000000"
        target = "a.py" if unit_id.endswith("a") else "b.py"
        (Path(workspace_path) / target).write_text(f"VALUE = '{unit_id}'\n", encoding="utf-8")
        with self.lock:
            self.prompts[unit_id] = prompt
            self.sessions[unit_id] = session
        return completed_result(task_id, unit_id, session, workspace_path)

    def continue_session(
        self, *, session_id: str, prompt: str, artifact_path: str, workspace_path: str
    ) -> OpenCodeRunResult:
        task_id = self._field(prompt, "task_id")
        unit_id = self._field(prompt, "unit_id")
        with self.lock:
            self.continued.append((unit_id, session_id))
        (Path(workspace_path) / "a.py").write_text("VALUE = 'repaired'\n", encoding="utf-8")
        return completed_result(task_id, unit_id, session_id, workspace_path)


def test_fanout_is_dynamic_and_not_fixed_to_four(tmp_path):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=[f"file-{i}.py" for i in range(12)])
    units = [unit(base, envelope, envelope_sha, f"u{i:02d}", [f"file-{i}.py"]) for i in range(12)]
    decision = plan_fanout(
        units,
        CapacityLease(
            requested_concurrency=12,
            provider_available=20,
            workspace_available=20,
            controller_attention_limit=20,
        ),
    )
    assert decision["effective_capacity"] == 12
    assert len(decision["admitted_units"]) == 12
    assert decision["fixed_worker_pool"] is False


def test_dependency_overlap_and_control_pressure_clamp(tmp_path):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base)
    units = [
        unit(base, envelope, envelope_sha, "ua", ["a.py"], priority=10),
        unit(base, envelope, envelope_sha, "ua2", ["a.py"], priority=5),
        unit(base, envelope, envelope_sha, "ub", ["b.py"]),
        unit(base, envelope, envelope_sha, "uc", ["nested"], dependencies_ready=False),
    ]
    decision = plan_fanout(
        units,
        CapacityLease(
            requested_concurrency=10,
            provider_available=10,
            workspace_available=10,
            controller_attention_limit=5,
            active_workers=1,
            pending_verifications=1,
            pending_repairs=1,
            pending_candidates=1,
        ),
    )
    assert decision["effective_capacity"] == 1
    assert decision["admitted_units"] == ["ua"]
    assert decision["deferred_mutation_overlap"] == ["ua2"]
    assert "uc" in decision["blocked_dependencies"]
    assert "ub" in decision["deferred_capacity"]
    assert decision["control_pressure"]["control_pressure"] == 4


def test_directory_boundaries_are_treated_as_mutation_overlap(tmp_path):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base)
    decision = plan_fanout(
        [
            unit(base, envelope, envelope_sha, "parent", ["nested"]),
            unit(base, envelope, envelope_sha, "child", ["nested/c.py"]),
        ],
        CapacityLease(2, 2, 2, 2),
    )
    assert len(decision["admitted_units"]) == 1
    assert len(decision["deferred_mutation_overlap"]) == 1


def test_worker_bootstrap_contains_ref_hash_not_full_envelope_body(tmp_path):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    marker = "SHOULD_NOT_ENTER_SOL_CONTEXT_987654"
    envelope_sha = make_envelope(envelope, base, marker=marker)
    parsed = ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    prompt = build_worker_bootstrap(parsed, WorkspaceLease("ws-1", "/tmp/ws-1", base))
    assert str(envelope) in prompt
    assert envelope_sha in prompt
    assert marker not in prompt
    assert "authorized_mutation_paths" in prompt


def test_worker_bootstrap_identifies_deepseek_l2_and_model_adaptation_without_envelope_body(
    tmp_path,
):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    marker = "SHOULD_NOT_ENTER_SOL_CONTEXT_987654"
    envelope_sha = make_envelope(envelope, base, marker=marker)
    parsed = ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    prompt = build_worker_bootstrap(parsed, WorkspaceLease("ws-1", "/tmp/ws-1", base))
    assert "DeepSeek V4 Flash" in prompt
    assert "bounded L2 Task Engineer" in prompt
    assert "model_adaptation" in prompt
    assert (
        "role_contract, task_local_invariants, known_failure_guards, execution_strategy, forbidden_inferences, repair_policy"
        in prompt
    )
    assert "authorized_mutation_paths" in prompt
    assert "Do not commit, push, merge, approve, integrate, or spawn a replacement model" in prompt
    assert "one evidence-guided same-unit repair and no blind retry or auto-chain" in prompt
    assert marker not in prompt
    assert envelope.read_text(encoding="utf-8") not in prompt


def test_export_attestation_accepts_truncated_large_session_after_complete_info(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_id = "ses_test_export_00000000"
    info = {
        "id": session_id,
        "directory": str(workspace.resolve()),
        "model": {"providerID": PROVIDER_ID, "id": MODEL_ID},
        "version": "1.18.18",
    }
    prefix = json.dumps({"info": info}, separators=(",", ":"))
    truncated = prefix[:-1] + ',"messages":[{"text":"' + ("x" * 70000)

    class Result:
        returncode = 0
        stdout = truncated
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    transport = OpenCodeDeepSeekTransport(executable="opencode")
    attestation = transport._export_attestation(session_id, str(workspace))
    assert attestation["provider_id"] == PROVIDER_ID
    assert attestation["model_id"] == MODEL_ID
    assert attestation["directory"] == str(workspace.resolve())
    assert attestation["version"] == "1.18.18"


def test_worker_result_rejects_approval_or_other_extra_claims():
    invalid = {
        "schema": "external_intelligence_worker_result.v1",
        "task_id": "task-1",
        "unit_id": "ua",
        "status": "IMPLEMENTATION_COMPLETED",
        "summary": "done",
        "approved": True,
    }
    with pytest.raises(FanoutError, match="WORKER_RESULT_PARSE_FAILED"):
        parse_worker_result(json.dumps(invalid), task_id="task-1", unit_id="ua")


def test_worker_result_accepts_json_wrapped_in_prose_prefix():
    payload = {
        "schema": "external_intelligence_worker_result.v1",
        "task_id": "task-1",
        "unit_id": "ua",
        "status": "IMPLEMENTATION_COMPLETED",
        "summary": "created exactly one file",
    }
    prose = "All checks pass: pytest 1 passed, no commit.\n\n" + json.dumps(payload)
    parsed = parse_worker_result(prose, task_id="task-1", unit_id="ua")
    assert parsed["status"] == "IMPLEMENTATION_COMPLETED"
    assert parsed["summary"] == "created exactly one file"


def test_worker_result_rejects_multiple_embedded_json_objects():
    payload = {
        "schema": "external_intelligence_worker_result.v1",
        "task_id": "task-1",
        "unit_id": "ua",
        "status": "IMPLEMENTATION_COMPLETED",
        "summary": "done",
    }
    ambiguous = json.dumps({"schema": "decoy"}) + "\n\n" + json.dumps(payload)
    with pytest.raises(FanoutError, match="WORKER_RESULT_PARSE_FAILED"):
        parse_worker_result(ambiguous, task_id="task-1", unit_id="ua")


def test_envelope_sha_scope_and_forbidden_paths_fail_closed(tmp_path):
    _, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"], forbidden=["forbidden"])
    allocator = GitWorktreeAllocator(tmp_path / "repo", tmp_path / "workspaces")
    store = FanoutStore(tmp_path / "state")
    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=allocator, store=store, transport=EditingTransport()
    )

    widened = runtime.run(
        [unit(base, envelope, envelope_sha, "ub", ["b.py"])],
        CapacityLease(1, 1, 1, 1),
    )
    assert "UNIT_SCOPE_WIDENING_FORBIDDEN" in widened["errors"]["ub"]

    bad_sha = runtime.run(
        [unit(base, envelope, "f" * 64, "ua", ["a.py"])],
        CapacityLease(1, 1, 1, 1),
    )
    assert "ENVELOPE_SHA256_MISMATCH" in bad_sha["errors"]["ua"]


def test_worktree_allocator_produces_unique_clean_exact_base_workspaces(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base)
    allocator = GitWorktreeAllocator(repo, tmp_path / "workspaces")
    a = allocator.allocate(
        ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    )
    b = allocator.allocate(
        ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ub", ["b.py"]))
    )
    assert a.workspace_id != b.workspace_id
    assert a.path != b.path
    assert _git(Path(a.path), "rev-parse", "HEAD") == base
    assert _git(Path(b.path), "rev-parse", "HEAD") == base
    assert _git(Path(a.path), "status", "--porcelain=v1") == ""
    assert _git(Path(b.path), "status", "--porcelain=v1") == ""


def test_store_journals_before_dispatch_and_blocks_blind_replay(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base)
    parsed = ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    workspace = GitWorktreeAllocator(repo, tmp_path / "workspaces").allocate(parsed)
    store = FanoutStore(tmp_path / "state")
    attempt = store.prepare_initial(parsed, workspace)
    assert attempt["state"] == "PREPARED" and attempt["retry_safe"] is True
    store.mark_dispatching(attempt)
    with pytest.raises(FanoutError, match="FANOUT_RECONCILIATION_REQUIRED"):
        store.prepare_initial(parsed, workspace)


def test_session_binding_forbids_cross_unit_reuse(tmp_path):
    store = FanoutStore(tmp_path / "state")
    session = "ses_test_owner_00000000"
    store.claim_session(session, task_id="task-1", unit_id="ua", workspace_id="ws-a")
    store.assert_session_owner(session, task_id="task-1", unit_id="ua", workspace_id="ws-a")
    with pytest.raises(FanoutError, match="SESSION_BINDING_CONFLICT"):
        store.assert_session_owner(session, task_id="task-1", unit_id="ub", workspace_id="ws-b")


def test_exact_model_is_constructor_enforced():
    with pytest.raises(FanoutError, match="MODEL_SUBSTITUTION_FORBIDDEN"):
        OpenCodeDeepSeekTransport(model="some-other/model")


def test_opencode_transport_parses_1_18_domain_event_stream(monkeypatch, tmp_path):
    """Installed OpenCode 1.18.x emits domain events (message.part.updated).

    Production must parse this shape, not only the legacy flat per-part shape.
    """
    calls = []
    session = "ses_domain_event_00000001"
    workspace = str(tmp_path.resolve())

    class FakePopen:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.returncode = 0
            self.pid = 9999
            self.stdout = None
            self.stderr = None
            calls.append(argv)

        def communicate(self, timeout=None):
            def part_event(part):
                return json.dumps({
                    "type": "message.part.updated",
                    "id": "e",
                    "data": {
                        "sessionID": session,
                        "part": part,
                        "time": 0,
                    },
                })

            events = "\n".join([
                part_event({"type": "step-start", "id": "p1"}),
                part_event({"type": "reasoning", "text": "thinking", "id": "p2"}),
                part_event({
                    "type": "text",
                    "text": json.dumps({
                        "schema": "external_intelligence_worker_result.v1",
                        "task_id": "task-1",
                        "unit_id": "ua",
                        "status": "BLOCKED",
                        "summary": "no mutation",
                    }),
                    "id": "p3",
                }),
                part_event({"type": "step-finish", "id": "p4", "reason": "completed"}),
            ])
            return events, ""

    def fake_run(argv, **kwargs):
        assert argv[:2] == ["opencode", "export"]
        exported = {
            "info": {
                "id": session,
                "directory": workspace,
                "version": "1.18.18",
                "model": {"providerID": PROVIDER_ID, "id": MODEL_ID},
            }
        }
        return SimpleNamespace(
            returncode=0, stdout="Exporting session\n" + json.dumps(exported), stderr=""
        )

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    transport = OpenCodeDeepSeekTransport(executable="opencode")
    result = transport.run_new(prompt="p", artifact_path="/tmp/envelope", workspace_path=workspace)
    assert result.status == "COMPLETED"
    assert result.session_id == session
    assert result.provider_id == PROVIDER_ID and result.model_id == MODEL_ID
    assert result.directory == workspace
    assert result.response_text.startswith('{"schema":')


def test_opencode_new_and_continue_bind_exact_model_session_and_directory(monkeypatch, tmp_path):
    calls = []
    session = "ses_test_transport_00000000"
    workspace = str(tmp_path.resolve())

    class FakePopen:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.returncode = 0
            self.pid = 9999
            self.stdout = None
            self.stderr = None
            calls.append(argv)

        def communicate(self, timeout=None):
            events = "\n".join([
                json.dumps({"type": "step_start", "sessionID": session, "part": {}}),
                json.dumps({
                    "type": "text",
                    "sessionID": session,
                    "part": {
                        "text": json.dumps({
                            "schema": "external_intelligence_worker_result.v1",
                            "task_id": "task-1",
                            "unit_id": "ua",
                            "status": "BLOCKED",
                            "summary": "no mutation",
                        })
                    },
                }),
                json.dumps({"type": "step_finish", "sessionID": session, "part": {}}),
            ])
            return events, ""

    def fake_run(argv, **kwargs):
        assert argv[:2] == ["opencode", "export"]
        exported = {
            "info": {
                "id": session,
                "directory": workspace,
                "version": "1.18.18",
                "model": {"providerID": PROVIDER_ID, "id": MODEL_ID},
            }
        }
        return SimpleNamespace(
            returncode=0, stdout="Exporting session\n" + json.dumps(exported), stderr=""
        )

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    transport = OpenCodeDeepSeekTransport(executable="opencode")
    first = transport.run_new(prompt="p", artifact_path="/tmp/envelope", workspace_path=workspace)
    second = transport.continue_session(
        session_id=session, prompt="p2", artifact_path="/tmp/repair", workspace_path=workspace
    )
    assert first.status == "COMPLETED" and second.status == "COMPLETED"
    assert first.session_id == second.session_id == session
    assert first.provider_id == PROVIDER_ID and first.model_id == MODEL_ID
    assert calls[0][2] == "p"
    assert calls[0].index("-f") > 2
    assert calls[0][calls[0].index("--model") + 1] == MODEL
    assert "--session" not in calls[0]
    assert calls[1][calls[1].index("--session") + 1] == session
    assert calls[0][calls[0].index("--dir") + 1] == workspace


def test_opencode_model_attestation_mismatch_is_outcome_unknown(monkeypatch, tmp_path):
    session = "ses_test_badmodel_00000000"
    workspace = str(tmp_path.resolve())

    class FakePopen:
        returncode = 0
        pid = 9999
        stdout = None
        stderr = None

        def __init__(self, argv, **kwargs):
            pass

        def communicate(self, timeout=None):
            return "\n".join([
                json.dumps({"type": "text", "sessionID": session, "part": {"text": "{}"}}),
                json.dumps({"type": "step_finish", "sessionID": session, "part": {}}),
            ]), ""

    def fake_run(argv, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "info": {
                    "id": session,
                    "directory": workspace,
                    "version": "1.18.18",
                    "model": {"providerID": PROVIDER_ID, "id": "wrong-model"},
                }
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = OpenCodeDeepSeekTransport().run_new(
        prompt="p", artifact_path="x", workspace_path=workspace
    )
    assert result.status == "OPENCODE_ATTESTATION_UNKNOWN"
    assert result.process_started is True
    assert result.outcome_unknown is True
    assert result.retry_safe is False


def test_runtime_parallel_units_get_fresh_sessions_workspaces_and_candidate_receipts(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "artifacts" / "envelope.json"
    marker = "NO_CONTROLLER_COPY_12345"
    envelope_sha = make_envelope(envelope, base, marker=marker)
    transport = EditingTransport()
    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=transport,
    )
    result = runtime.run(
        [
            unit(base, envelope, envelope_sha, "ua", ["a.py"]),
            unit(base, envelope, envelope_sha, "ub", ["b.py"]),
        ],
        CapacityLease(10, 10, 10, 10),
    )
    assert result["errors"] == {}
    assert set(result["receipts"]) == {"ua", "ub"}
    a = result["receipts"]["ua"]
    b = result["receipts"]["ub"]
    assert a["schema"] == WORKER_RECEIPT_SCHEMA
    assert a["status"] == b["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert a["claim_ceiling"] == b["claim_ceiling"] == CLAIM_CEILING
    assert a["session_id"] != b["session_id"]
    assert a["workspace_id"] != b["workspace_id"]
    assert a["workspace_path"] != b["workspace_path"]
    assert a["candidate_commit"] and b["candidate_commit"]
    assert len(a["candidate_diff_sha256"]) == 64
    assert marker not in transport.prompts["ua"]
    assert marker not in transport.prompts["ub"]
    assert _git(Path(a["workspace_path"]), "status", "--porcelain=v1") == ""
    assert _git(Path(b["workspace_path"]), "status", "--porcelain=v1") == ""


def test_prestart_retry_safe_failure_allows_one_fresh_exact_attempt(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])

    class RetryOnceTransport(EditingTransport):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def run_new(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return OpenCodeRunResult(
                    status="OPENCODE_NOT_FOUND",
                    process_started=False,
                    retry_safe=True,
                )
            return super().run_new(**kwargs)

    store = FanoutStore(tmp_path / "state")
    transport = RetryOnceTransport()
    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=store,
        transport=transport,
    )
    args = [unit(base, envelope, envelope_sha, "ua", ["a.py"])]
    first = runtime.run(args, CapacityLease(1, 1, 1, 1))
    assert first["errors"]["ua"] == "OPENCODE_NOT_FOUND"
    failed = json.loads(next((tmp_path / "state" / "attempts").glob("*.json")).read_text())
    assert failed["state"] == "RETRY_SAFE"
    assert failed["retry_safe"] is True

    second = runtime.run(args, CapacityLease(1, 1, 1, 1))
    assert second["errors"] == {}
    assert second["receipts"]["ua"]["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    attempt = json.loads(next((tmp_path / "state" / "attempts").glob("*.json")).read_text())
    assert attempt["state"] == "COMPLETED"
    assert attempt["retry_count"] == 1
    assert transport.calls == 2


def test_completed_units_do_not_starve_deferred_capacity_on_next_run(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py", "b.py"])
    transport = EditingTransport()
    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=transport,
    )
    args = [
        unit(base, envelope, envelope_sha, "ua", ["a.py"], priority=10),
        unit(base, envelope, envelope_sha, "ub", ["b.py"]),
    ]
    first = runtime.run(args, CapacityLease(1, 1, 1, 1))
    assert set(first["receipts"]) == {"ua"}
    assert first["decision"]["deferred_capacity"] == ["ub"]

    second = runtime.run(args, CapacityLease(1, 1, 1, 1))
    assert second["errors"] == {}
    assert set(second["receipts"]) == {"ua", "ub"}
    assert second["decision"]["completed_units"] == ["ua"]
    assert second["decision"]["admitted_units"] == ["ub"]



def test_runtime_outcome_unknown_requires_reconciliation_and_no_second_start(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])

    class UnknownTransport:
        def run_new(self, **kwargs):
            return OpenCodeRunResult(
                status="OPENCODE_OUTCOME_UNKNOWN",
                process_started=True,
                outcome_unknown=True,
                retry_safe=False,
            )

    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=UnknownTransport(),
    )
    result = runtime.run(
        [unit(base, envelope, envelope_sha, "ua", ["a.py"])], CapacityLease(1, 1, 1, 1)
    )
    assert "FANOUT_RECONCILIATION_REQUIRED" in result["errors"]["ua"]
    attempt_path = next((tmp_path / "state" / "attempts").glob("*.json"))
    attempt = json.loads(attempt_path.read_text())
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["retry_safe"] is False


def test_runtime_recovers_dispatching_attempt_from_durable_session_without_second_start(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])
    parsed = ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    allocator = GitWorktreeAllocator(repo, tmp_path / "workspaces")
    workspace = allocator.allocate(parsed)
    store = FanoutStore(tmp_path / "state")
    attempt = store.mark_dispatching(store.prepare_initial(parsed, workspace))
    assert attempt["state"] == "DISPATCHING"
    (Path(workspace.path) / "a.py").write_text("VALUE = 'recovered'\n", encoding="utf-8")

    class RecoveryTransport:
        run_new_calls = 0
        reconcile_calls = 0

        def run_new(self, **kwargs):
            self.run_new_calls += 1
            raise AssertionError("recovery must not start a second worker")

        def reconcile_workspace(self, *, workspace_path):
            self.reconcile_calls += 1
            return completed_result("task-1", "ua", "ses_recovered_00000000", workspace_path)

    transport = RecoveryTransport()
    runtime = AdaptiveDeepSeekFanoutRuntime(allocator=allocator, store=store, transport=transport)
    result = runtime.run([parsed], CapacityLease(1, 1, 1, 1))
    assert result["errors"] == {}
    receipt = result["receipts"]["ua"]
    assert receipt["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert receipt["session_id"] == "ses_recovered_00000000"
    assert receipt["changed_paths"] == ["a.py"]
    assert transport.run_new_calls == 0
    assert transport.reconcile_calls == 1
    durable_attempt = json.loads(next((tmp_path / "state" / "attempts").glob("*.json")).read_text())
    assert durable_attempt["state"] == "COMPLETED"
    assert _git(Path(receipt["workspace_path"]), "status", "--porcelain=v1") == ""

    replay = runtime.run([parsed], CapacityLease(1, 1, 1, 1))
    assert replay["errors"] == {}
    assert replay["receipts"]["ua"]["receipt_id"] == receipt["receipt_id"]
    assert transport.run_new_calls == 0
    assert transport.reconcile_calls == 1


def test_runtime_reconciliation_fails_closed_without_terminal_session(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])
    parsed = ExecutionUnit.from_mapping(unit(base, envelope, envelope_sha, "ua", ["a.py"]))
    allocator = GitWorktreeAllocator(repo, tmp_path / "workspaces")
    workspace = allocator.allocate(parsed)
    store = FanoutStore(tmp_path / "state")
    store.mark_dispatching(store.prepare_initial(parsed, workspace))

    class NonTerminalTransport:
        def run_new(self, **kwargs):
            raise AssertionError("must not redispatch")

        def reconcile_workspace(self, *, workspace_path):
            raise FanoutError("OPENCODE_RECONCILE_NOT_TERMINAL")

    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=allocator, store=store, transport=NonTerminalTransport()
    )
    result = runtime.run([parsed], CapacityLease(1, 1, 1, 1))
    assert result["errors"]["ua"] == "OPENCODE_RECONCILE_NOT_TERMINAL"
    attempt = json.loads(next((tmp_path / "state" / "attempts").glob("*.json")).read_text())
    assert attempt["state"] == "DISPATCHING"
    assert not list((tmp_path / "state" / "receipts").glob("*.json"))


def test_candidate_capture_rejects_out_of_scope_worker_mutation(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py", "b.py"])

    class BadTransport:
        def run_new(self, *, prompt, artifact_path, workspace_path):
            (Path(workspace_path) / "b.py").write_text("BAD = True\n", encoding="utf-8")
            return completed_result("task-1", "ua", "ses_bad_scope_00000000", workspace_path)

    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=BadTransport(),
    )
    result = runtime.run(
        [unit(base, envelope, envelope_sha, "ua", ["a.py"])], CapacityLease(1, 1, 1, 1)
    )
    assert result["errors"] == {}
    assert result["receipts"]["ua"]["status"] == "WORKER_BLOCKED"
    attempt = json.loads(next((tmp_path / "state" / "attempts").glob("*.json")).read_text())
    assert attempt["state"] == "TERMINAL_BLOCKED"
    assert result["receipts"]["ua"]["worker_summary"] == "OUT_OF_SCOPE_MUTATION:b.py"


def test_empty_and_unauthorized_deletion_are_terminal_hard_blocks(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])

    class NoChangeTransport(EditingTransport):
        def run_new(self, **kwargs):
            task_id = self._field(kwargs["prompt"], "task_id")
            unit_id = self._field(kwargs["prompt"], "unit_id")
            session = f"ses_test_{unit_id}_00000000"
            return completed_result(task_id, unit_id, session, kwargs["workspace_path"])

    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state-empty"),
        transport=NoChangeTransport(),
    )
    empty = runtime.run(
        [unit(base, envelope, envelope_sha, "ua", ["a.py"])], CapacityLease(1, 1, 1, 1)
    )
    assert empty["errors"] == {}
    assert empty["receipts"]["ua"]["worker_summary"] == "EMPTY_IMPLEMENTATION_RESULT"

    class DeleteTransport(EditingTransport):
        def run_new(self, **kwargs):
            Path(kwargs["workspace_path"], "a.py").unlink()
            return completed_result(
                self._field(kwargs["prompt"], "task_id"),
                self._field(kwargs["prompt"], "unit_id"),
                "ses_test_delete_00000000",
                kwargs["workspace_path"],
            )

    delete_runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces-delete"),
        store=FanoutStore(tmp_path / "state-delete"),
        transport=DeleteTransport(),
    )
    deleted = delete_runtime.run(
        [unit(base, envelope, envelope_sha, "ua", ["a.py"])], CapacityLease(1, 1, 1, 1)
    )
    assert deleted["errors"] == {}
    assert deleted["receipts"]["ua"]["worker_summary"] == "DELETION_NOT_AUTHORIZED"


def test_same_unit_repair_continues_exact_session_and_creates_child_candidate(tmp_path):
    repo, base = make_repo(tmp_path)
    envelope = tmp_path / "envelope.json"
    envelope_sha = make_envelope(envelope, base, allowed=["a.py"])
    transport = EditingTransport()
    store = FanoutStore(tmp_path / "state")
    runtime = AdaptiveDeepSeekFanoutRuntime(
        allocator=GitWorktreeAllocator(repo, tmp_path / "workspaces"),
        store=store,
        transport=transport,
    )
    initial = runtime.run(
        [unit(base, envelope, envelope_sha, "ua", ["a.py"])], CapacityLease(1, 1, 1, 1)
    )["receipts"]["ua"]
    repair = tmp_path / "repair.json"
    repair.write_text('{"schema":"repair_delta.v2","instruction":"repair a.py"}', encoding="utf-8")
    import hashlib

    repair_sha = hashlib.sha256(repair.read_bytes()).hexdigest()
    child = runtime.continue_repair(
        initial, repair_id="r1", repair_ref=str(repair), repair_sha256=repair_sha
    )
    assert child["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert child["session_id"] == initial["session_id"]
    assert child["workspace_id"] == initial["workspace_id"]
    assert child["parent_receipt_id"] == initial["receipt_id"]
    assert child["candidate_commit"] != initial["candidate_commit"]
    assert child["parent_commit"] == initial["candidate_commit"]
    assert transport.continued == [("ua", initial["session_id"])]


def test_repair_session_cannot_be_rebound_to_another_unit(tmp_path):
    store = FanoutStore(tmp_path / "state")
    session = "ses_bound_repair_00000000"
    store.claim_session(session, task_id="task-1", unit_id="ua", workspace_id="ws-a")
    fake = {
        "schema": WORKER_RECEIPT_SCHEMA,
        "status": "CANDIDATE_READY_FOR_VERIFICATION",
        "task_id": "task-1",
        "unit_id": "ub",
        "provider": "opencode",
        "model": MODEL,
        "session_id": session,
        "workspace_id": "ws-b",
        "workspace_path": "/tmp/ws-b",
        "candidate_commit": "a" * 40,
        "receipt_id": "r",
    }
    with pytest.raises(FanoutError, match="SESSION_BINDING_CONFLICT"):
        store.prepare_repair(fake, repair_id="r1", repair_ref="x", repair_sha256="b" * 64)
