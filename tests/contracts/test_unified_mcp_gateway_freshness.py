"""Contract tests for the ``nexus_gateway_status`` freshness semantics.

``repository_drift`` is informational; only runtime source drift triggers
``reload_required``, and only an action contract change or a fail-closed
contract evaluation triggers ``action_review_required``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[2])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.orchestrator import unified_mcp_gateway as gateway_module  # noqa: E402
from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    FRESHNESS_SEMANTICS_REVISION,
    UnifiedMCPGateway,
    _action_contract_digest,
    _action_contract_fingerprint,
    _evaluate_freshness,
    _hash_source_paths,
    _permission_enforcement_fingerprint,
)

SHA40_A = "a" * 40
SHA40_B = "b" * 40
DIGEST_1 = "1" * 64
DIGEST_2 = "2" * 64
DIGEST_3 = "3" * 64
DIGEST_4 = "4" * 64


class _StubService:
    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self, *, include_details=False):
        return {"actionable_count": 0, "details_included": include_details, "tasks": []}


def test_gateway_process_binds_explicit_canonical_source_root():
    root = Path(repo_root).resolve()
    command = (
        "import json; "
        "from nexus.orchestrator import lifecycle_guards, self_hosted_task_service, unified_mcp_gateway; "
        "print(json.dumps({"
        "'guard': str(lifecycle_guards.CANONICAL_SOURCE_ROOT), "
        "'service': str(self_hosted_task_service.CANONICAL_SOURCE_ROOT), "
        "'gateway': str(unified_mcp_gateway.CANONICAL_SOURCE_ROOT), "
        "'head': unified_mcp_gateway.SERVER_REPO_HEAD_AT_START, "
        "'runtime_paths': len(unified_mcp_gateway.RUNTIME_SOURCE_PATHS)"
        "}, sort_keys=True))"
    )
    env = dict(os.environ)
    env["NEXUS_CANONICAL_SOURCE_ROOT"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["guard"] == str(root)
    assert payload["service"] == str(root)
    assert payload["gateway"] == str(root)
    assert (
        payload["head"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    assert payload["runtime_paths"] > 0


def test_gateway_process_rejects_activation_root_for_different_loaded_source(tmp_path):
    other_root = tmp_path / "other-checkout"
    other_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=other_root, check=True)
    env = dict(os.environ)
    env["NEXUS_CANONICAL_SOURCE_ROOT"] = str(other_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", "from nexus.orchestrator import unified_mcp_gateway"],
        cwd=Path(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH" in result.stderr


def test_head_drift_only_is_informational():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_B,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_2,
        action_sha_current=DIGEST_2,
    )
    assert result["repository_drift"] is True
    assert result["runtime_source_drift"] is False
    assert result["reload_required"] is False
    assert result["action_review_required"] is False
    assert result["reload_reasons"] == []


def test_tampered_head_only_signal_cannot_invent_action_review():
    inputs = {
        "repo_head_at_start": SHA40_A,
        "repo_head_current": SHA40_A,
        "runtime_sha_at_start": DIGEST_1,
        "runtime_sha_current": DIGEST_1,
        "action_sha_at_start": DIGEST_2,
        "action_sha_current": DIGEST_2,
    }
    baseline = _evaluate_freshness(**inputs)

    # Mutate only the untrusted repository-HEAD signal.  The consumer must
    # project that change solely as informational repository drift; it cannot
    # manufacture an action/permission review or a runtime reload.
    inputs["repo_head_current"] = SHA40_B
    tampered = _evaluate_freshness(**inputs)

    assert baseline["repository_drift"] is False
    assert tampered == {**baseline, "repository_drift": True}


def test_runtime_drift_triggers_reload_only():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
    )
    assert result["repository_drift"] is False
    assert result["runtime_source_drift"] is True
    assert result["reload_required"] is True
    assert result["action_review_required"] is False
    assert "runtime_source_changed" in result["reload_reasons"]


def test_action_contract_drift_requires_review():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_4,
    )
    assert result["runtime_source_drift"] is True
    assert result["reload_required"] is True
    assert result["action_review_required"] is True
    assert result["reload_reasons"] == ["runtime_source_changed"]
    assert "action_definition_changed" in result["review_reasons"]


def test_action_contract_fail_closed_requires_review():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current="",
        action_contract_ok=False,
        action_contract_reasons=("action_contract_source_unreadable:OSError",),
    )
    assert result["reload_required"] is True
    assert result["action_review_required"] is True
    assert "action_contract_source_unreadable:OSError" in result["review_reasons"]
    assert "action_contract_source_unreadable:OSError" not in result["reload_reasons"]


def test_no_drift_is_stable():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_2,
        action_sha_current=DIGEST_2,
    )
    assert result["repository_drift"] is False
    assert result["runtime_source_drift"] is False
    assert result["reload_required"] is False
    assert result["action_review_required"] is False
    assert result["reload_reasons"] == []


def test_action_contract_digest_rejects_unparseable_source():
    assert _action_contract_digest("def broken(:\n") is None
    digest, ok, reasons = _action_contract_fingerprint(source="def broken(:\n")
    assert digest == ""
    assert ok is False
    assert "action_contract_source_unparseable" in reasons


def test_action_contract_fingerprint_fails_closed_on_unreadable_source(tmp_path):
    digest, ok, reasons = _action_contract_fingerprint(root=tmp_path)
    assert digest == ""
    assert ok is False
    assert any(reason.startswith("action_contract_source_unreadable") for reason in reasons)


_SAMPLE_SOURCE = """\
PERMISSION_POLICY = {"revision": "v1"}
PERMISSION_POLICY_REVISION = "v1"
TASK_CONTRACT_REVISION = "v1"
LIFECYCLE_REVISION = "v1"
LIFECYCLE_STATE_SCHEMA_REVISION = "v1"

class UnifiedMCPGateway:
    @staticmethod
    def tool_specs():
        return [{"name": "nexus_gateway_status", "inputSchema": {"type": "object"}}]
"""


def test_action_contract_digest_is_sensitive_to_permission_policy():
    base = _action_contract_digest(_SAMPLE_SOURCE)
    changed = _action_contract_digest(
        _SAMPLE_SOURCE.replace('"revision": "v1"', '"revision": "v2"')
    )
    assert base is not None
    assert base != changed


def test_action_contract_digest_is_sensitive_to_tool_specs():
    base = _action_contract_digest(_SAMPLE_SOURCE)
    changed = _action_contract_digest(
        _SAMPLE_SOURCE.replace("nexus_gateway_status", "nexus_gateway_status_v2")
    )
    assert base is not None
    assert base != changed


def test_action_contract_digest_is_insensitive_to_implementation():
    base = _action_contract_digest(_SAMPLE_SOURCE)
    changed = _action_contract_digest(_SAMPLE_SOURCE + "\ndef _search(self):\n    pass\n")
    assert base == changed


def test_real_action_contract_fingerprint_matches_frozen_start():
    digest, ok, reasons = _action_contract_fingerprint()
    assert ok is True
    assert reasons == ()
    assert digest == gateway_module.ACTION_CONTRACT_SHA256_AT_START


def test_hash_source_paths_is_deterministic(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("x = 1\n", encoding="utf-8")
    first = _hash_source_paths((path,), root=tmp_path)
    second = _hash_source_paths((path,), root=tmp_path)
    assert first == second
    assert len(first) == 64


def test_hash_source_paths_detects_content_change(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("x = 1\n", encoding="utf-8")
    before = _hash_source_paths((path,), root=tmp_path)
    path.write_text("x = 2\n", encoding="utf-8")
    after = _hash_source_paths((path,), root=tmp_path)
    assert before != after


def test_hash_source_paths_detects_missing_file(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("x = 1\n", encoding="utf-8")
    before = _hash_source_paths((path,), root=tmp_path)
    path.unlink()
    after = _hash_source_paths((path,), root=tmp_path)
    assert before != after


def test_loaded_runtime_source_paths_are_canonical_python_sources():
    root = gateway_module.CANONICAL_SOURCE_ROOT.resolve()
    # ``RUNTIME_SOURCE_PATHS`` is the import-time snapshot.  The live module
    # registry may legitimately contain additional canonical modules after
    # pytest has collected another suite, so do not compare it with a later
    # enumeration of ``sys.modules`` here.
    paths = gateway_module.RUNTIME_SOURCE_PATHS
    assert paths
    for path in paths:
        assert path.suffix == ".py"
        path.relative_to(root)
        assert "__pycache__" not in path.parts
        assert "tests" not in path.parts
    assert paths == tuple(sorted(set(paths), key=lambda path: path.as_posix()))


def test_late_canonical_import_cannot_mutate_frozen_runtime_source_snapshot():
    before_paths = gateway_module.RUNTIME_SOURCE_PATHS
    before_digest = gateway_module.RUNTIME_SOURCE_SHA256_AT_START

    # This is the hostile collection-order case: importing the EIA automation
    # surface after Gateway startup adds canonical modules to ``sys.modules``.
    # Those later imports must not rewrite the Gateway's frozen baseline.
    __import__("nexus.services.external_intelligence_automation")

    assert gateway_module.RUNTIME_SOURCE_PATHS == before_paths
    assert gateway_module.RUNTIME_SOURCE_SHA256_AT_START == before_digest
    assert _hash_source_paths(gateway_module.RUNTIME_SOURCE_PATHS) == before_digest


def test_gateway_status_has_freshness_fields_and_is_stable():
    gateway = UnifiedMCPGateway(service=_StubService())
    status = gateway._gateway_status()
    assert status["schema"] == "nexus.mcp_gateway_status.v1"
    assert status["freshness_semantics_revision"] == FRESHNESS_SEMANTICS_REVISION
    assert status["freshness_semantics_revision"] == "nexus.gateway_freshness.v3"
    assert set(status) >= {
        "repository_drift",
        "runtime_source_sha256_at_start",
        "runtime_source_sha256_current",
        "runtime_source_drift",
        "action_definition_sha256_at_start",
        "action_definition_sha256_current",
        "action_contract_sha256_at_start",
        "action_contract_sha256_current",
        "permission_enforcement_sha256_at_start",
        "permission_enforcement_sha256_current",
        "action_definition_review_required",
        "permission_review_required",
        "action_review_required",
        "review_reasons",
        "reload_required",
        "reload_reasons",
    }
    assert status["runtime_source_drift"] is False
    assert status["reload_required"] is False
    assert status["action_definition_review_required"] is False
    assert status["permission_review_required"] is False
    assert status["action_review_required"] is False
    assert status["runtime_source_sha256_at_start"] == status["runtime_source_sha256_current"]
    assert status["action_contract_sha256_at_start"] == status["action_contract_sha256_current"]
    assert (
        status["action_definition_sha256_at_start"]
        == gateway_module.ACTION_CONTRACT_SHA256_AT_START
    )
    assert (
        status["permission_enforcement_sha256_at_start"]
        == status["permission_enforcement_sha256_current"]
    )
    assert (
        status["permission_enforcement_sha256_at_start"]
        == gateway_module.PERMISSION_ENFORCEMENT_SHA256_AT_START
    )


def test_gateway_status_reflects_runtime_drift(monkeypatch):
    monkeypatch.setattr(gateway_module, "_hash_source_paths", lambda paths: DIGEST_4)
    monkeypatch.setattr(
        gateway_module,
        "_action_contract_fingerprint",
        lambda **kw: (gateway_module.ACTION_CONTRACT_SHA256_AT_START, True, ()),
    )
    gateway = UnifiedMCPGateway(service=_StubService())
    status = gateway._gateway_status()
    assert status["runtime_source_drift"] is True
    assert status["reload_required"] is True
    assert status["action_review_required"] is False
    assert "runtime_source_changed" in status["reload_reasons"]


def test_gateway_status_reflects_action_contract_drift(monkeypatch):
    monkeypatch.setattr(gateway_module, "_hash_source_paths", lambda paths: DIGEST_4)
    monkeypatch.setattr(
        gateway_module, "_action_contract_fingerprint", lambda **kw: (DIGEST_3, True, ())
    )
    gateway = UnifiedMCPGateway(service=_StubService())
    status = gateway._gateway_status()
    assert status["runtime_source_drift"] is True
    assert status["reload_required"] is True
    assert status["action_review_required"] is True
    assert status["reload_reasons"] == ["runtime_source_changed"]
    assert "action_definition_changed" in status["review_reasons"]


def test_gateway_status_action_contract_fail_closed(monkeypatch):
    monkeypatch.setattr(gateway_module, "_hash_source_paths", lambda paths: DIGEST_4)
    monkeypatch.setattr(
        gateway_module,
        "_action_contract_fingerprint",
        lambda **kw: ("", False, ("action_contract_source_unreadable:OSError",)),
    )
    gateway = UnifiedMCPGateway(service=_StubService())
    status = gateway._gateway_status()
    assert status["reload_required"] is True
    assert status["action_review_required"] is True
    assert "action_contract_source_unreadable:OSError" in status["review_reasons"]
    assert "action_contract_source_unreadable:OSError" not in status["reload_reasons"]


def _write_permission_tree(
    tmp_path, guard_body: str, action_body: str = "class LifecycleAction:\n    pass\n"
) -> None:
    guards_dir = tmp_path / "nexus" / "orchestrator"
    contracts_dir = tmp_path / "nexus" / "contracts"
    guards_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (guards_dir / "lifecycle_guards.py").write_text(guard_body, encoding="utf-8")
    (contracts_dir / "lifecycle_action.py").write_text(action_body, encoding="utf-8")


def test_permission_enforcement_digest_is_sensitive_to_semantic_ast_change(tmp_path):
    _write_permission_tree(tmp_path, "def pre_action_guard(*, action, target):\n    return True\n")
    base, ok, reasons = _permission_enforcement_fingerprint(root=tmp_path)
    assert ok is True
    assert reasons == ()
    _write_permission_tree(tmp_path, "def pre_action_guard(*, action, target):\n    return False\n")
    changed, ok, reasons = _permission_enforcement_fingerprint(root=tmp_path)
    assert ok is True
    assert base != changed


def test_permission_enforcement_digest_ignores_comments_and_formatting(tmp_path):
    _write_permission_tree(
        tmp_path, "# header comment\ndef pre_action_guard(*, action, target):\n    return True\n"
    )
    base, ok, _ = _permission_enforcement_fingerprint(root=tmp_path)
    assert ok is True
    _write_permission_tree(
        tmp_path, "\n\ndef pre_action_guard(*,action,target):\n    return True\n"
    )
    changed, ok, _ = _permission_enforcement_fingerprint(root=tmp_path)
    assert ok is True
    assert base == changed


def test_permission_enforcement_unreadable_fails_closed(tmp_path):
    digest, ok, reasons = _permission_enforcement_fingerprint(root=tmp_path)
    assert digest == ""
    assert ok is False
    assert any(reason.startswith("permission_enforcement_source_unreadable") for reason in reasons)


def test_permission_enforcement_unparseable_fails_closed(tmp_path):
    _write_permission_tree(tmp_path, "def broken(:\n")
    digest, ok, reasons = _permission_enforcement_fingerprint(root=tmp_path)
    assert digest == ""
    assert ok is False
    assert any(reason.startswith("permission_enforcement_source_unparseable") for reason in reasons)


def test_real_permission_enforcement_fingerprint_matches_frozen_start():
    digest, ok, reasons = _permission_enforcement_fingerprint()
    assert ok is True
    assert reasons == ()
    assert digest == gateway_module.PERMISSION_ENFORCEMENT_SHA256_AT_START


def test_action_definition_change_requires_definition_review_only():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_4,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["reload_required"] is False
    assert result["action_definition_review_required"] is True
    assert result["permission_review_required"] is False
    assert result["action_review_required"] is True
    assert "action_definition_changed" in result["review_reasons"]


def test_permission_change_requires_permission_review():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_2,
    )
    assert result["reload_required"] is False
    assert result["action_definition_review_required"] is False
    assert result["permission_review_required"] is True
    assert result["action_review_required"] is True
    assert "permission_enforcement_changed" in result["review_reasons"]


def test_runtime_implementation_change_requires_reload_without_review():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["reload_required"] is True
    assert result["action_definition_review_required"] is False
    assert result["permission_review_required"] is False
    assert result["action_review_required"] is False
    assert "runtime_source_changed" in result["reload_reasons"]
    assert result["review_reasons"] == []


def test_head_only_drift_requires_neither_reload_nor_review():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_B,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["repository_drift"] is True
    assert result["reload_required"] is False
    assert result["action_definition_review_required"] is False
    assert result["permission_review_required"] is False
    assert result["action_review_required"] is False
    assert result["review_reasons"] == []


def test_action_review_reason_not_in_reload_reasons():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_4,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["action_review_required"] is True
    assert result["reload_required"] is False
    assert result["reload_reasons"] == []
    assert result["review_reasons"] == ["action_definition_changed"]


def test_permission_review_reason_not_in_reload_reasons():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_2,
    )
    assert result["permission_review_required"] is True
    assert result["reload_required"] is False
    assert result["reload_reasons"] == []
    assert result["review_reasons"] == ["permission_enforcement_changed"]


def test_action_fingerprint_failure_only_appears_in_review_reasons():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current="",
        action_contract_ok=False,
        action_contract_reasons=("action_contract_source_unparseable:SyntaxError",),
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["action_review_required"] is True
    assert result["reload_required"] is False
    assert result["reload_reasons"] == []
    assert "action_contract_source_unparseable:SyntaxError" in result["review_reasons"]


def test_permission_fingerprint_failure_only_appears_in_review_reasons():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_1,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current="",
        permission_contract_ok=False,
        permission_contract_reasons=("permission_enforcement_source_unreadable:OSError",),
    )
    assert result["permission_review_required"] is True
    assert result["reload_required"] is False
    assert result["reload_reasons"] == []
    assert "permission_enforcement_source_unreadable:OSError" in result["review_reasons"]


def test_runtime_drift_is_only_reload_reason():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_3,
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_1,
    )
    assert result["reload_required"] is True
    assert result["action_review_required"] is False
    assert result["reload_reasons"] == ["runtime_source_changed"]
    assert result["review_reasons"] == []


def test_combined_runtime_and_review_drift_keeps_reason_sets_separate():
    result = _evaluate_freshness(
        repo_head_at_start=SHA40_A,
        repo_head_current=SHA40_A,
        runtime_sha_at_start=DIGEST_1,
        runtime_sha_current=DIGEST_2,
        action_sha_at_start=DIGEST_3,
        action_sha_current=DIGEST_4,
        action_contract_ok=False,
        action_contract_reasons=("action_contract_source_unreadable:OSError",),
        permission_sha_at_start=DIGEST_1,
        permission_sha_current=DIGEST_2,
        permission_contract_ok=False,
        permission_contract_reasons=("permission_enforcement_source_unparseable:SyntaxError",),
    )
    assert result["reload_required"] is True
    assert result["action_review_required"] is True
    assert result["reload_reasons"] == ["runtime_source_changed"]
    assert "action_contract_source_unreadable:OSError" in result["review_reasons"]
    assert "permission_enforcement_source_unparseable:SyntaxError" in result["review_reasons"]
    assert "action_definition_changed" in result["review_reasons"]
    assert "permission_enforcement_changed" in result["review_reasons"]
    assert all(reason not in result["reload_reasons"] for reason in result["review_reasons"])
