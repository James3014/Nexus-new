from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

import scripts.ops.external_intelligence_service as service_module
from nexus.core.exit_codes import NexusExitCode
from scripts.ops.external_intelligence_service import (
    READINESS_SUCCESS_THRESHOLD,
    GhIssueTransport,
    ServiceConfig,
    ServiceError,
    ServiceReadiness,
    _parse_launchctl,
    _safe_error,
    build_automation,
    load_config,
    plist_xml,
    refresh_remote_main,
    render_comment,
    run_once,
    service_status,
    write_service_receipt,
)


class FakeGh:
    def __init__(self, issues, comments=None):
        self.issues = issues
        self.comments = list(comments or [])
        self.calls = []

    def list_open_labeled(self, repository, label):
        self.calls.append((repository, label))
        return list(self.issues.get(repository, []))

    def list_comments(self, repository, issue_number):
        return [
            {"id": i + 1, "body": c[2]}
            for i, c in enumerate(self.comments)
            if c[0] == repository and c[1] == issue_number
        ]

    def comment(self, repository, issue_number, body):
        self.comments.append((repository, issue_number, body))


class FakeAutomation:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_issue(self, repository, issue_number, title, body):
        self.calls.append((repository, issue_number, title, body))
        return dict(self.result)


def _config(tmp_path, **overrides):
    values = dict(
        repositories=("o/r",),
        repository_roots={"o/r": str(tmp_path / "repo")},
        state_root=tmp_path / "state",
        workspace_root=tmp_path / "workspaces",
        opencli_profile="test-profile",
        opencode_executable="/tmp/opencode",
    )
    values.update(overrides)
    return ServiceConfig(**values)


def _config_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({
            "repositories": ["o/r"],
            "repository_roots": {"o/r": str(tmp_path / "repo")},
            "state_root": str(tmp_path / "state"),
            "workspace_root": str(tmp_path / "workspaces"),
        }),
        encoding="utf-8",
    )
    return path


def _complete(reuse=False, publication_state="COMPLETED"):
    pub_payload = {
        "task_id": "t1",
        "candidate_commit": "a" * 40,
        "candidate_tree": "b" * 40,
        "verification_state": "PASS",
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "acceptance_packet_ref": "state/a.json",
        "acceptance_packet_sha256": "c" * 64,
        "next_action": "independent_acceptance",
        "stop_condition": "acceptance_failed",
        "claim_ceiling": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
    }
    from nexus.services.external_intelligence_automation import compute_publication_id

    pub_id = compute_publication_id("o/r", 1, "h" * 64, pub_payload)
    return {
        "state": "COMPLETE",
        "reuse": reuse,
        "identity_hash": "h" * 64,
        "publication": pub_payload,
        "publication_record": {
            "publication_id": pub_id,
            "state": publication_state if reuse else "PREPARED",
            "marker": f"<!-- nexus-external-intelligence:{pub_id} -->",
            "payload": pub_payload,
        },
    }


def test_load_config_is_strict_and_profile_is_configurable(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({
            "repositories": ["o/r"],
            "repository_roots": {"o/r": str(tmp_path / "repo")},
            "state_root": str(tmp_path / "state"),
            "workspace_root": str(tmp_path / "workspaces"),
            "opencli_profile": "profile-alias",
        }),
        encoding="utf-8",
    )
    loaded = load_config(cfg)
    assert loaded.opencli_profile == "profile-alias"
    assert loaded.opencode_executable == "opencode"
    raw = json.loads(cfg.read_text())
    raw["secret_surprise"] = True
    cfg.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ServiceError):
        load_config(cfg)


def test_semantic_backend_defaults_to_opencli(tmp_path):
    loaded = load_config(_config_file(tmp_path))

    assert getattr(loaded, "semantic_backend", None) == "opencli"


def test_unknown_semantic_backend_is_rejected_explicitly(tmp_path):
    config_path = _config_file(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["semantic_backend"] = "unknown"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ServiceError, match="CONFIG_SEMANTIC_BACKEND_INVALID"):
        load_config(config_path)

    with pytest.raises(ServiceError, match="CONFIG_SEMANTIC_BACKEND_INVALID"):
        build_automation(_config(tmp_path, semantic_backend="unknown"), "o/r")


def test_open_swe_backend_requires_explicit_model_binding(tmp_path):
    config = _config(tmp_path, semantic_backend="open_swe")

    with pytest.raises(ServiceError, match="CONFIG_OPEN_SWE_MODEL_BINDING_REQUIRED"):
        build_automation(config, "o/r")


def test_worker_backend_defaults_to_opencode(tmp_path):
    loaded = load_config(_config_file(tmp_path))

    assert loaded.worker_backend == "opencode"


def test_unknown_worker_backend_is_rejected(tmp_path):
    config_path = _config_file(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["worker_backend"] = "unknown"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ServiceError, match="CONFIG_WORKER_BACKEND_INVALID"):
        load_config(config_path)


def test_build_automation_selects_open_swe_worker_only_when_explicit(tmp_path, monkeypatch):
    calls = []

    class FakeOpenSWEWorkerTransport:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        service_module,
        "OpenSWEWorkerTransport",
        FakeOpenSWEWorkerTransport,
        raising=False,
    )
    config = _config(
        tmp_path,
        worker_backend="open_swe",
        open_swe_model_provider="google_genai",
        open_swe_model="gemini-test",
    )

    automation = build_automation(config, "o/r")

    assert isinstance(automation.c_runtime.transport, FakeOpenSWEWorkerTransport)
    assert calls == [
        {
            "model_provider": "google_genai",
            "model_id": "gemini-test",
            "executable": "nexus-open-swe-runtime",
            "runtime_state_root": tmp_path / "state" / "open_swe_runtime",
            "require_worker_binding": True,
        }
    ]


def test_load_config_binds_open_swe_provider_and_model(tmp_path):
    config_path = _config_file(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw.update(
        semantic_backend="open_swe",
        open_swe_model_provider="google_genai",
        open_swe_model="gemini-test",
    )
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_config(config_path)

    assert loaded.semantic_backend == "open_swe"
    assert loaded.open_swe_model_provider == "google_genai"
    assert loaded.open_swe_model == "gemini-test"
    assert loaded.open_swe_executable == "nexus-open-swe-runtime"


def test_load_config_rejects_open_swe_without_complete_model_binding(tmp_path):
    config_path = _config_file(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["semantic_backend"] = "open_swe"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ServiceError, match="CONFIG_OPEN_SWE_MODEL_BINDING_REQUIRED"):
        load_config(config_path)


def test_build_automation_keeps_opencli_as_default(tmp_path):
    automation = build_automation(_config(tmp_path), "o/r")

    assert isinstance(
        automation.sidecar.transport, service_module.OpenCLIExternalIntelligenceTransport
    )


def test_build_automation_selects_open_swe_only_when_explicit(tmp_path, monkeypatch):
    calls = []

    class FakeOpenSWETransport:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        service_module,
        "OpenSWEExternalIntelligenceTransport",
        FakeOpenSWETransport,
        raising=False,
    )
    config = _config(
        tmp_path,
        semantic_backend="open_swe",
        open_swe_model_provider="google_genai",
        open_swe_model="gemini-test",
    )

    automation = build_automation(config, "o/r")

    assert isinstance(automation.sidecar.transport, FakeOpenSWETransport)
    assert calls == [
        {
            "repository_root": (tmp_path / "repo").resolve(),
            "model_provider": "google_genai",
            "model_id": "gemini-test",
            "executable": "nexus-open-swe-runtime",
            "runtime_state_root": tmp_path / "state" / "open_swe_runtime",
        }
    ]


def test_load_config_rejects_empty_open_swe_external_executable(tmp_path):
    config_path = _config_file(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw.update(
        semantic_backend="open_swe",
        open_swe_model_provider="google_genai",
        open_swe_model="gemini-test",
        open_swe_executable="",
    )
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ServiceError, match="CONFIG_OPEN_SWE_EXECUTABLE_REQUIRED"):
        load_config(config_path)


# Historical exact-base node retained across the in-process -> external-runtime
# ownership move. A missing external runtime remains fail-closed at construction.
def test_build_automation_fails_closed_when_open_swe_optional_runtime_is_missing(
    tmp_path, monkeypatch
):
    module = importlib.import_module("nexus.services.open_swe_external_intelligence")

    class MissingOpenSWETransport:
        def __init__(self, **_kwargs):
            raise module.OpenSWEExternalIntelligenceError("OPEN_SWE_RUNTIME_NOT_FOUND")

    monkeypatch.setattr(
        service_module,
        "OpenSWEExternalIntelligenceTransport",
        MissingOpenSWETransport,
        raising=False,
    )
    config = _config(
        tmp_path,
        semantic_backend="open_swe",
        open_swe_model_provider="google_genai",
        open_swe_model="gemini-test",
    )

    with pytest.raises(ServiceError, match="OPEN_SWE_RUNTIME_NOT_FOUND"):
        build_automation(config, "o/r")


def test_run_once_processes_at_most_one_issue_and_publishes_compact_result(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "later", "body": "b"},
            {"number": 1, "title": "first", "body": "a"},
        ]
    })
    automation = FakeAutomation(_complete())
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert result["issue_number"] == 1
    assert len(automation.calls) == 1
    assert len(gh.comments) == 1
    body = gh.comments[0][2]
    assert "External Intelligence automation completed" in body
    assert "envelope" not in body.lower()
    assert "prompt" not in body.lower()


def test_reused_completion_does_not_duplicate_comment(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "first", "body": "a"}]})
    automation = FakeAutomation(_complete(reuse=True))
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert result["status"] == "COMPLETE"
    assert gh.comments == []


def test_run_once_skips_reused_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return _complete(reuse=True)
            return _complete()

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "already-done", "body": "a"},
        ]
    })
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_run_once_skips_pre_dispatch_blocked_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {
                    "state": "BLOCKED",
                    "error": "TASK_CARD_HASH_MISMATCH",
                    "semantic_dispatched": False,
                }
            return _complete()

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "blocked", "body": "a"},
        ]
    })
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_run_once_skips_source_lineage_blocked_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {
                    "state": "BLOCKED",
                    "error": "MAIN_SHA_LINEAGE_MISMATCH",
                    "semantic_dispatched": False,
                }
            return _complete()

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "blocked-lineage", "body": "a"},
        ]
    })
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


@pytest.mark.parametrize(
    "disposition",
    [
        {"state": "REPAIR_BUDGET_EXHAUSTED", "semantic_dispatched": True},
        {"state": "UNIT_REPAIR_REQUIRED", "semantic_dispatched": True},
        {"state": "COMPOSITION_REPAIR_REQUIRED", "semantic_dispatched": True},
        {"state": "SCOPE_DELTA_REQUIRED", "semantic_dispatched": True},
        {
            "state": "RECONCILIATION_REQUIRED",
            "prior_state": "CLOSURE_DISPATCHING",
            "semantic_dispatched": True,
        },
    ],
)
def test_run_once_skips_terminal_or_reconcile_issue_to_reach_eligible_next(tmp_path, disposition):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return dict(disposition)
            return _complete()

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "durable-stop", "body": "a"},
        ]
    })
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_run_once_skips_dispatched_blocked_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {
                    "state": "BLOCKED",
                    "stage": "CLOSURE",
                    "closure_status": "CLOSURE_NON_TERMINAL_FAILURE",
                    "semantic_dispatched": True,
                }
            return _complete()

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "dispatched-blocked", "body": "a"},
        ]
    })
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert result["status"] == "COMPLETE"
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2
    assert "External Intelligence automation completed" in gh.comments[0][2]


def test_idle_when_no_labeled_issue(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": []})
    refreshes = []
    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: None,
        refresh_fn=lambda r, repo: refreshes.append((r, repo)),
    )
    assert result == {"status": "IDLE"}
    assert gh.calls == [("o/r", "nexus:external-intelligence")]
    assert refreshes == []


def test_publication_disabled_never_comments(tmp_path):
    config = _config(tmp_path, publication_enabled=False)
    gh = FakeGh({"o/r": [{"number": 1, "title": "first", "body": "a"}]})
    automation = FakeAutomation(_complete())
    run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert gh.comments == []


def test_refresh_remote_main_fetches_exact_main_ref(tmp_path):
    bare = tmp_path / "o" / "r.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Actor"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "actor@example.com"],
        cwd=work,
        check=True,
        capture_output=True,
    )
    (work / "file.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "A"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=work, check=True, capture_output=True)
    sha_A = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()

    runtime = tmp_path / "runtime"
    subprocess.run(["git", "clone", str(bare), str(runtime)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Runtime"], cwd=runtime, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runtime@example.com"],
        cwd=runtime,
        check=True,
        capture_output=True,
    )

    # Actor advances bare main to commit B
    (work / "file.txt").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "B"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=work, check=True, capture_output=True)
    sha_B = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()

    # Pre-check runtime tracking is at A
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "refs/remotes/origin/main"], cwd=runtime, text=True
        ).strip()
        == sha_A
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip()
        == sha_A
    )

    # Set remote URL to test repository form
    # Execute refresh_remote_main
    refresh_remote_main(runtime, str(bare))

    # Post-check: remote-tracking ref updated to B, worktree HEAD stays at A, worktree clean
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "refs/remotes/origin/main"], cwd=runtime, text=True
        ).strip()
        == sha_B
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip()
        == sha_A
    )
    assert (
        subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=runtime, text=True).strip()
        == ""
    )


def test_refresh_remote_main_failure_blocks_run_once(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "title", "body": "body"}]})

    def failing_refresh(_r, _repo):
        raise ServiceError("REMOTE_MAIN_REFRESH_FAILED")

    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: FakeAutomation(_complete()),
        refresh_fn=failing_refresh,
    )
    assert result["status"] == "BLOCKED"
    assert result["result"]["error"] == "REMOTE_MAIN_REFRESH_FAILED"
    assert result["result"]["semantic_dispatched"] is False
    assert gh.comments == []


def test_refresh_repository_identity_mismatch_blocks_run_once(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "title", "body": "body"}]})

    def mismatch_refresh(_r, _repo):
        raise ServiceError("REPOSITORY_IDENTITY_MISMATCH")

    result = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: FakeAutomation(_complete()),
        refresh_fn=mismatch_refresh,
    )
    assert result["status"] == "BLOCKED"
    assert result["result"]["error"] == "REPOSITORY_IDENTITY_MISMATCH"
    assert result["result"]["semantic_dispatched"] is False
    assert gh.comments == []


def test_critical_regression_eia_unattended_freshness_end_to_end(tmp_path):
    # End-to-end test simulating daemon running unattended across main advancement
    bare = tmp_path / "James3014" / "Nexus-new.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )

    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Actor"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "actor@example.com"],
        cwd=work,
        check=True,
        capture_output=True,
    )

    # Initial commit A has task card A
    card_dir = work / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "x.md").write_text("# task card A\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "commit A"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=work, check=True, capture_output=True)
    sha_A = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()

    # Runtime repo cloned at commit A
    runtime = tmp_path / "runtime"
    subprocess.run(["git", "clone", str(bare), str(runtime)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Runtime"], cwd=runtime, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runtime@example.com"],
        cwd=runtime,
        check=True,
        capture_output=True,
    )

    # Upstream actor advances remote main to commit B with task card B
    card_b_text = (
        "# Task Card: task-b\n\n"
        "- task_id: `task-b`\n"
        "- status: ACTIVE\n\n"
        "## Allowed files\n"
        "- `nexus/a.py`\n\n"
        "## Verification commands\n"
        "```bash\n"
        "python3 --version\n"
        "git status\n"
        "```\n"
    )
    (card_dir / "x.md").write_text(card_b_text, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "commit B"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=work, check=True, capture_output=True)
    sha_B = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    hash_B = hashlib.sha256(card_b_text.encode("utf-8")).hexdigest()

    # Issue contract referencing commit B and hash B
    contract = {
        "schema": "nexus.external_intelligence_issue.v1",
        "task_id": "task-b",
        "revision": "r1",
        "main_sha": sha_B,
        "task_card_ref": "tasks/x.md",
        "task_card_hash": hash_B,
        "pipeline_mode": "FULL_PIPELINE",
        "execution_units": [{"unit_id": "u1", "mutation_paths": ["nexus/a.py"]}],
        "unit_verifiers": {"u1": [{"id": "u1", "argv": ["python3", "--version"]}]},
        "whole_verifiers": [{"id": "whole", "argv": ["git", "status"]}],
        "requested_concurrency": 1,
        "ready": True,
        "contract_ready": True,
    }
    body = "prose\n```nexus-external-intelligence\n" + json.dumps(contract) + "\n```\n"

    repo_identity = "James3014/Nexus-new"
    config = ServiceConfig(
        repositories=(repo_identity,),
        repository_roots={repo_identity: str(runtime)},
        state_root=tmp_path / "state",
        workspace_root=tmp_path / "workspaces",
    )
    gh = FakeGh({
        repo_identity: [{"number": 201, "title": "New work on advanced main", "body": body}]
    })

    # Run real run_once with real refresh_remote_main and real automation
    class FakeSidecar:
        def __init__(self, store):
            self.store = store
            self.calls = []

        def analyze(self, record, sources):
            self.calls.append((record, list(sources)))
            envelope = {"schema": "external_execution_envelope.v1", "x": 1}
            req_sha = "b" * 64
            p = self.store.root / "envelopes" / f"{req_sha}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")), encoding="utf-8"
            )
            envelope_sha = hashlib.sha256(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            return {
                "status": "COMPLETED",
                "receipt_id": "r-1",
                "request": {"request_sha256": req_sha},
                "envelope_sha256": envelope_sha,
            }

    class FakeC:
        def run(self, units, lease):
            return {
                "receipts": {"u1": {"status": "CANDIDATE_READY_FOR_VERIFICATION", "unit_id": "u1"}},
                "errors": {},
                "run_sha256": "c" * 64,
            }

    class FakeD:
        def close_task(self, **kwargs):
            return {
                "status": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
                "run_id": "d" * 64,
                "control_capsule": {
                    "task_id": "task-b",
                    "candidate_commit": sha_B,
                    "candidate_tree": "t" * 40,
                    "verification_state": "PASS",
                    "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
                    "acceptance_packet_ref": "state/a.json",
                    "acceptance_packet_sha256": "3" * 64,
                    "next_action": "independent_acceptance",
                    "stop_condition": "acceptance_failed",
                    "claim_ceiling": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
                },
            }

    def factory(cfg, repo_name):
        auto = build_automation(cfg, repo_name)
        auto.sidecar = FakeSidecar(auto.intelligence_store)
        auto.c_runtime = FakeC()
        auto.d_runtime = FakeD()
        return auto

    # Pre-state: runtime tracking is at A
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "refs/remotes/origin/main"], cwd=runtime, text=True
        ).strip()
        == sha_A
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip()
        == sha_A
    )

    result = run_once(config, gh=gh, automation_factory=factory)

    assert result["status"] == "COMPLETE"
    assert result["issue_number"] == 201
    assert len(gh.comments) == 1
    assert "External Intelligence automation completed" in gh.comments[0][2]

    # Post-state: runtime tracking ref refreshed to B, HEAD stayed at A, worktree clean
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "refs/remotes/origin/main"], cwd=runtime, text=True
        ).strip()
        == sha_B
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip()
        == sha_A
    )
    assert (
        subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=runtime, text=True).strip()
        == ""
    )


def test_plist_is_local_launchagent_daemon_and_has_no_hardcoded_profile(tmp_path):
    xml = plist_xml(tmp_path / "config.json")
    assert "com.nexus.external-intelligence" in xml
    assert "external_intelligence_service" in xml
    assert "daemon" in xml
    assert "64b57tak" not in xml
    assert "/Users/jameschen/.opencode/bin" in xml


def test_plist_derives_logs_from_state_root(tmp_path):
    state_root = tmp_path / "state"
    xml = plist_xml(tmp_path / "config.json", state_root=state_root)
    assert f"{state_root}/service/daemon.stdout.log" in xml
    assert f"{state_root}/service/daemon.stderr.log" in xml
    assert "/dev/null" not in xml


def test_service_receipt_is_atomic_restrictive_and_identity_bound(tmp_path):
    path = tmp_path / "state" / "service" / "daemon.json"
    write_service_receipt(
        path,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.STARTING.value,
            "run_id": "run-1",
            "pid": 123,
            "source_path": "/tmp/service.py",
            "source_sha256": "a" * 64,
            "config_path": "/tmp/config.json",
            "config_sha256": "b" * 64,
            "started_at": 99.0,
            "heartbeat_at": 100.0,
            "successful_polls": 1,
            "last_error": None,
        },
    )
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "run-1"
    assert os.stat(path).st_mode & 0o077 == 0
    assert not list(path.parent.glob("*.tmp"))


def test_service_error_surface_is_bounded_and_redacted():
    safe = _safe_error(ServiceError("GH_COMMAND_FAILED"))
    assert safe == {"type": "ServiceError", "code": "GH_COMMAND_FAILED"}
    redacted = _safe_error(ServiceError("token=secret-value"))
    assert redacted["code"] == "ServiceError"
    assert "secret-value" not in json.dumps(redacted)


def test_service_status_registered_alone_never_ready(tmp_path):
    config = _config_file(tmp_path)

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    result = service_status(config, launchctl_runner=launchctl, process_snapshot=lambda: [])
    assert result["status"] == ServiceReadiness.STARTING.value
    assert result["ready"] is False


def test_service_status_reconciles_identity_heartbeat_and_last_exit(tmp_path):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    source_sha = hashlib.sha256(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scripts/ops/external_intelligence_service.py")
        .read_bytes()
    ).hexdigest()
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    write_service_receipt(
        receipt,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_path": str(
                Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
            ),
            "source_sha256": source_sha,
            "config_path": str(config.resolve()),
            "config_sha256": config_sha,
            "started_at": 99.0,
            "heartbeat_at": 100.0,
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
            "last_error": None,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    expected_command = (
        f"{Path(sys.executable).resolve()} -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )

    good = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert good["status"] == ServiceReadiness.READY.value
    assert good["ready"] is True

    bad_exit = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 1\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert bad_exit["status"] == ServiceReadiness.DEGRADED.value

    stale = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, expected_command)],
        now=100.0 + 10_000,
        receipt_path=receipt,
    )
    assert stale["status"] == ServiceReadiness.STALE.value


def test_parse_launchctl_handles_numeric_never_exited_and_missing():
    parsed_zero = _parse_launchctl(
        subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )
    )
    assert parsed_zero["registered"] is True
    assert parsed_zero["state"] == "running"
    assert parsed_zero["pid"] == 123
    assert parsed_zero["last_exit_code"] == 0
    assert parsed_zero["last_exit_state"] == "EXITED_WITH_CODE"

    parsed_never = _parse_launchctl(
        subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        )
    )
    assert parsed_never["registered"] is True
    assert parsed_never["state"] == "running"
    assert parsed_never["pid"] == 123
    assert parsed_never["last_exit_code"] is None
    assert parsed_never["last_exit_state"] == "NEVER_EXITED"

    parsed_nonzero = _parse_launchctl(
        subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 256\n", ""
        )
    )
    assert parsed_nonzero["last_exit_code"] == 256
    assert parsed_nonzero["last_exit_state"] == "EXITED_WITH_CODE"

    parsed_missing = _parse_launchctl(
        subprocess.CompletedProcess(["launchctl"], 0, "state = running\npid = 123\n", "")
    )
    assert parsed_missing["last_exit_code"] is None
    assert parsed_missing["last_exit_state"] == "UNKNOWN_OR_MISSING"

    parsed_malformed = _parse_launchctl(
        subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = unknown_status\n", ""
        )
    )
    assert parsed_malformed["last_exit_code"] is None
    assert parsed_malformed["last_exit_state"] == "UNKNOWN_OR_MISSING"


def test_service_status_handles_launchd_never_exited_and_regression_cases(tmp_path):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    source_sha = hashlib.sha256(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scripts/ops/external_intelligence_service.py")
        .read_bytes()
    ).hexdigest()
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()

    def make_receipt(
        *,
        status=ServiceReadiness.READY.value,
        pid=123,
        polls=READINESS_SUCCESS_THRESHOLD,
        heartbeat=100.0,
    ):
        write_service_receipt(
            receipt,
            {
                "schema": "nexus.external_intelligence_daemon_receipt.v1",
                "status": status,
                "run_id": "run-1",
                "pid": pid,
                "source_path": str(
                    Path(__file__).resolve().parents[2]
                    / "scripts/ops/external_intelligence_service.py"
                ),
                "source_sha256": source_sha,
                "config_path": str(config.resolve()),
                "config_sha256": config_sha,
                "started_at": 99.0,
                "heartbeat_at": heartbeat,
                "successful_polls": polls,
                "last_error": None,
            },
        )

    make_receipt()
    expected_command = (
        f"{Path(sys.executable).resolve()} -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )

    # CASE A — explicit never exited: READY when all other gates pass
    never_exited = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert never_exited["status"] == ServiceReadiness.READY.value
    assert never_exited["ready"] is True

    # CASE B — numeric zero: READY
    num_zero = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert num_zero["status"] == ServiceReadiness.READY.value
    assert num_zero["ready"] is True

    # CASE C — numeric nonzero: DEGRADED
    num_nonzero = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 1\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert num_nonzero["status"] == ServiceReadiness.DEGRADED.value
    assert num_nonzero["ready"] is False

    # CASE D — missing last exit code: DEGRADED (fail-closed)
    missing_exit = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert missing_exit["status"] == ServiceReadiness.DEGRADED.value
    assert missing_exit["ready"] is False

    # CASE D.2 — malformed last exit code: DEGRADED (fail-closed)
    malformed_exit = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = abnormal_term\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert malformed_exit["status"] == ServiceReadiness.DEGRADED.value
    assert malformed_exit["ready"] is False

    # Negative checks: never_exited does NOT bypass other gates
    # 1. Stale heartbeat
    stale_heartbeat = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.0 + 10_000,
        receipt_path=receipt,
    )
    assert stale_heartbeat["status"] == ServiceReadiness.STALE.value
    assert stale_heartbeat["ready"] is False

    # 2. PID mismatch
    make_receipt(pid=999)
    pid_mismatch = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert pid_mismatch["status"] == ServiceReadiness.IDENTITY_MISMATCH.value
    assert pid_mismatch["ready"] is False

    # 3. Successful polls below threshold
    make_receipt(polls=0)
    starting = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert starting["status"] == ServiceReadiness.STARTING.value
    assert starting["ready"] is False

    # 4. Receipt DEGRADED
    make_receipt(status=ServiceReadiness.DEGRADED.value)
    receipt_degraded = service_status(
        config,
        launchctl_runner=lambda *_args: subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = (never exited)\n", ""
        ),
        process_snapshot=lambda: [(123, expected_command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert receipt_degraded["status"] == ServiceReadiness.DEGRADED.value
    assert receipt_degraded["ready"] is False


def test_service_status_rejects_identity_mismatch_and_duplicate_processes(tmp_path):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    write_service_receipt(
        receipt,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_path": str(
                Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
            ),
            "source_sha256": "0" * 64,
            "config_path": str(config.resolve()),
            "config_sha256": "0" * 64,
            "started_at": time.time(),
            "heartbeat_at": time.time(),
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
            "last_error": None,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    expected_command = (
        f"{Path(sys.executable).resolve()} -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )

    mismatch = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, expected_command.replace("daemon", "daemon-worker", 1))],
        receipt_path=receipt,
    )
    assert mismatch["status"] == ServiceReadiness.IDENTITY_MISMATCH.value
    write_service_receipt(
        receipt,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_path": mismatch["source_path"],
            "source_sha256": mismatch["source_sha256"],
            "config_path": mismatch["config_path"],
            "config_sha256": mismatch["config_sha256"],
            "started_at": time.time(),
            "heartbeat_at": time.time(),
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
            "last_error": None,
        },
    )
    duplicate = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, expected_command), (456, expected_command)],
        receipt_path=receipt,
    )
    assert duplicate["status"] == ServiceReadiness.DUPLICATE_PROCESS.value
    wrong_config = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [
            (123, expected_command.replace(str(config.resolve()), str(tmp_path / "other.json")))
        ],
        receipt_path=receipt,
    )
    assert wrong_config["status"] == ServiceReadiness.DUPLICATE_PROCESS.value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", None),
        ("run_id", ""),
        ("run_id", 123),
        ("successful_polls", "two"),
        ("pid", "123"),
        ("heartbeat_at", "now"),
        ("schema", "wrong.schema"),
        ("source_sha256", "not-a-hash"),
        ("last_error", {"code": "only"}),
    ],
)
def test_service_status_malformed_receipt_fails_degraded_without_exception(tmp_path, field, value):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    payload = {
        "schema": "nexus.external_intelligence_daemon_receipt.v1",
        "status": ServiceReadiness.READY.value,
        "run_id": "run-1",
        "pid": 123,
        "source_path": str(
            Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
        ),
        "source_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
            ).read_bytes()
        ).hexdigest(),
        "config_path": str(config.resolve()),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "started_at": 100.0,
        "heartbeat_at": 100.0,
        "successful_polls": READINESS_SUCCESS_THRESHOLD,
        "last_error": None,
    }
    payload[field] = value
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    result = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [],
        receipt_path=receipt,
    )
    assert result["status"] == ServiceReadiness.DEGRADED.value
    assert result["ready"] is False


def test_render_comment_contains_only_compact_fields():
    result = _complete()
    result["raw_prompt"] = "SECRET_PROMPT"
    result["envelope"] = {"secret": "SECRET_ENVELOPE"}
    body = render_comment(result)
    assert "SECRET_PROMPT" not in body
    assert "SECRET_ENVELOPE" not in body
    assert "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE" in body


@pytest.mark.parametrize(
    ("command", "returncode", "expected_status", "expected_exit"),
    [
        ("start", 0, "STARTED", NexusExitCode.SUCCESS),
        ("start", 1, "START_FAILED", NexusExitCode.FAILED),
        ("stop", 0, "STOPPED", NexusExitCode.SUCCESS),
        ("stop", 1, "STOP_FAILED", NexusExitCode.FAILED),
        ("restart", 0, "RESTARTED", NexusExitCode.SUCCESS),
        ("restart", 1, "RESTART_FAILED", NexusExitCode.FAILED),
    ],
)
def test_main_maps_service_control_outcomes_to_canonical_exit_codes(
    monkeypatch, capsys, command, returncode, expected_status, expected_exit
):
    monkeypatch.setattr(service_module, "load_config", lambda _path: object())
    result = subprocess.CompletedProcess(["launchctl"], returncode, "", "bounded-detail")
    monkeypatch.setattr(service_module, "start", lambda _path: result)
    monkeypatch.setattr(service_module, "stop", lambda: result)

    exit_code = service_module.main([command, "--config", "/tmp/config.json"])

    assert exit_code == expected_exit
    assert json.loads(capsys.readouterr().out) == {
        "detail": "bounded-detail",
        "status": expected_status,
    }


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        ("IDLE", NexusExitCode.SUCCESS),
        ("COMPLETE", NexusExitCode.SUCCESS),
        ("FAILED", NexusExitCode.FAILED),
        ("UNRECOGNIZED_NON_SUCCESS", NexusExitCode.FAILED),
        ("REPAIR_BUDGET_EXHAUSTED", NexusExitCode.ESCALATED),
        ("UNIT_REPAIR_REQUIRED", NexusExitCode.ESCALATED),
        ("COMPOSITION_REPAIR_REQUIRED", NexusExitCode.ESCALATED),
        ("SCOPE_DELTA_REQUIRED", NexusExitCode.ESCALATED),
        ("RECONCILIATION_REQUIRED", NexusExitCode.ESCALATED),
        ("ESCALATED", NexusExitCode.ESCALATED),
        ("HUMAN_REVIEW", NexusExitCode.HUMAN_REVIEW),
        ("BLOCKED", NexusExitCode.HUMAN_REVIEW),
    ],
)
def test_main_maps_run_once_typed_outcomes_without_changing_payload(
    monkeypatch, capsys, status, expected_exit
):
    payload = {"status": status, "result": {"state": status}}
    monkeypatch.setattr(service_module, "load_config", lambda _path: object())
    monkeypatch.setattr(service_module, "run_once", lambda _config: payload)

    exit_code = service_module.main(["run-once", "--config", "/tmp/config.json"])

    assert exit_code == expected_exit
    assert json.loads(capsys.readouterr().out) == payload


def test_t3_prepared_persists_dispatching_posts_reads_back_and_next_poll_no_extra(tmp_path):
    config = _config(tmp_path)
    events: list[str] = []

    class SpyingStateStore:
        def __init__(self):
            self.records: dict[str, Any] = {}

        def update_publication_record(self, repository, issue_number, identity_hash, record):
            state = record.get("state")
            events.append(f"store:{state}")
            self.records[f"{repository}:{issue_number}"] = dict(record)
            return dict(record)

    class SpyingGh(FakeGh):
        def comment(self, repository, issue_number, body):
            events.append("gh:comment")
            super().comment(repository, issue_number, body)

    spy_store = SpyingStateStore()
    spying_gh = SpyingGh({"o/r": [{"number": 1, "title": "t", "body": "b"}]})

    automation = FakeAutomation(_complete(reuse=False))
    automation.state_store = spy_store

    # First poll: PREPARED -> persisted DISPATCHING -> one POST -> readback -> COMPLETED
    r1 = run_once(
        config,
        gh=spying_gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r1["status"] == "COMPLETE"
    assert len(spying_gh.comments) == 1
    assert "<!-- nexus-external-intelligence:" in spying_gh.comments[0][2]
    assert events == ["store:DISPATCHING", "gh:comment", "store:COMPLETED"]
    assert spy_store.records["o/r:1"]["state"] == "COMPLETED"

    # Second poll: next poll sees already completed publication -> no extra comments
    automation_reuse = FakeAutomation({
        **_complete(reuse=True),
        "publication_record": spy_store.records["o/r:1"],
    })
    automation_reuse.state_store = spy_store
    r2 = run_once(
        config,
        gh=spying_gh,
        automation_factory=lambda _c, _r: automation_reuse,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r2["status"] == "COMPLETE"
    assert len(spying_gh.comments) == 1


def test_t4_remote_accepted_before_local_confirm_reconciles_without_post(tmp_path):
    config = _config(tmp_path)
    pub_payload = _complete()["publication"]
    from nexus.services.external_intelligence_automation import compute_publication_id

    pub_id = compute_publication_id("o/r", 1, "", pub_payload)
    existing_comment_body = (
        f"<!-- nexus-external-intelligence:{pub_id} -->\n"
        "External Intelligence automation completed.\n"
    )
    gh = FakeGh(
        {"o/r": [{"number": 1, "title": "t", "body": "b"}]},
        comments=[("o/r", 1, existing_comment_body)],
    )
    # Restart from DISPATCHING/OUTCOME_UNKNOWN with marker present
    automation = FakeAutomation({
        "state": "COMPLETE",
        "publication": pub_payload,
        "publication_record": {
            "publication_id": pub_id,
            "state": "DISPATCHING",
            "payload": pub_payload,
        },
    })
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "COMPLETE"
    assert len(gh.comments) == 1  # create=0 (no new comment added)
    assert r["result"]["publication_record"]["state"] == "COMPLETED"


def test_t5_dispatching_or_outcome_unknown_with_zero_marker_fails_closed(tmp_path):
    config = _config(tmp_path)
    pub_payload = _complete()["publication"]
    from nexus.services.external_intelligence_automation import compute_publication_id

    pub_id = compute_publication_id("o/r", 1, "", pub_payload)
    gh = FakeGh({"o/r": [{"number": 1, "title": "t", "body": "b"}]})

    automation = FakeAutomation({
        "state": "COMPLETE",
        "publication": pub_payload,
        "publication_record": {
            "publication_id": pub_id,
            "state": "DISPATCHING",
            "payload": pub_payload,
        },
    })
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "PUBLICATION_UNCONFIRMED_ZERO_MARKER"
    assert len(gh.comments) == 0  # create=0


def test_t6_duplicate_marker_fails_closed(tmp_path):
    config = _config(tmp_path)
    pub_payload = _complete()["publication"]
    from nexus.services.external_intelligence_automation import compute_publication_id

    pub_id = compute_publication_id("o/r", 1, "", pub_payload)
    dup_body = (
        f"<!-- nexus-external-intelligence:{pub_id} -->\n"
        "External Intelligence automation completed.\n"
    )
    gh = FakeGh(
        {"o/r": [{"number": 1, "title": "t", "body": "b"}]},
        comments=[("o/r", 1, dup_body), ("o/r", 1, dup_body)],
    )
    automation = FakeAutomation({
        "state": "COMPLETE",
        "publication": pub_payload,
        "publication_record": {
            "publication_id": pub_id,
            "state": "PREPARED",
            "payload": pub_payload,
        },
    })
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "DUPLICATE_PUBLICATION_MARKER"
    assert len(gh.comments) == 2  # create=0 (no extra comments posted)


def test_persistence_failure_before_dispatching_causes_zero_comment(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "t", "body": "b"}]})

    class FailingStateStore:
        def update_publication_record(self, repository, issue_number, identity_hash, record):
            return None

    automation = FakeAutomation(_complete(reuse=False))
    automation.state_store = FailingStateStore()

    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: automation,
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "PUBLICATION_PERSISTENCE_FAILED"
    assert len(gh.comments) == 0


def test_legacy_reuse_without_publication_record_fails_closed_without_starving_next(tmp_path):
    config = _config(tmp_path)
    calls: list[int] = []

    class SequencedLegacyAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {
                    "state": "COMPLETE",
                    "reuse": True,
                    "publication": {"task_id": "t1"},
                }
            return _complete(reuse=False)

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "legacy", "body": "a"},
        ]
    })
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedLegacyAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert r["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_missing_list_comments_capability_fails_closed(tmp_path):
    config = _config(tmp_path)

    class BareGh:
        def list_open_labeled(self, repository, label):
            return [{"number": 1, "title": "t", "body": "b"}]

        def comment(self, repository, issue_number, body):
            pass

    r = run_once(
        config,
        gh=BareGh(),
        automation_factory=lambda _c, _r: FakeAutomation(_complete(reuse=False)),
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "GH_COMMENTS_LIST_FAILED"


def test_invalid_publication_state_fails_closed(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "t", "body": "b"}]})
    invalid_res = _complete(reuse=False)
    invalid_res["publication_record"]["state"] = "CORRUPTED_STATE"

    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: FakeAutomation(invalid_res),
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "PUBLICATION_STATE_INVALID"
    assert len(gh.comments) == 0


def test_post_readback_duplicate_marker_fails_closed(tmp_path):
    config = _config(tmp_path)
    pub_payload = _complete()["publication"]
    from nexus.services.external_intelligence_automation import compute_publication_id

    pub_id = compute_publication_id("o/r", 1, "h" * 64, pub_payload)
    dup_comment = f"<!-- nexus-external-intelligence:{pub_id} -->\ncompleted\n"

    class DuplicateOnReadbackGh(FakeGh):
        def comment(self, repository, issue_number, body):
            self.comments.append((repository, issue_number, dup_comment))
            self.comments.append((repository, issue_number, dup_comment))

    gh = DuplicateOnReadbackGh({"o/r": [{"number": 1, "title": "t", "body": "b"}]})
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: FakeAutomation(_complete(reuse=False)),
        refresh_fn=lambda _r, _repo: None,
    )
    assert r["status"] == "RECONCILIATION_REQUIRED"
    assert r["result"]["error"] == "DUPLICATE_PUBLICATION_MARKER"


def test_gh_issue_transport_list_comments_paginated_api(monkeypatch):
    gh = GhIssueTransport()
    recorded_argv: list[list[str]] = []

    def fake_run(argv):
        recorded_argv.append(argv)
        return json.dumps([
            [{"id": 10, "body": "comment 1"}, {"id": 11, "body": "comment 2"}],
            [{"id": 12, "body": "comment 3"}],
        ])

    monkeypatch.setattr(gh, "_run", fake_run)
    comments = gh.list_comments("James3014/Nexus-new", 438)

    assert len(recorded_argv) == 1
    argv = recorded_argv[0]
    assert argv == [
        "gh",
        "api",
        "repos/James3014/Nexus-new/issues/438/comments",
        "--paginate",
        "--slurp",
    ]
    assert len(comments) == 3
    assert [c["id"] for c in comments] == [10, 11, 12]


def test_publication_disabled_reused_complete_does_not_starve_next_eligible_issue(tmp_path):
    config = _config(tmp_path, publication_enabled=False)
    calls: list[int] = []

    class SequencedDisabledAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return _complete(reuse=True, publication_state="PREPARED")
            return _complete(reuse=False, publication_state="PREPARED")

    gh = FakeGh({
        "o/r": [
            {"number": 2, "title": "eligible", "body": "b"},
            {"number": 1, "title": "already-done", "body": "a"},
        ]
    })
    r = run_once(
        config,
        gh=gh,
        automation_factory=lambda _c, _r: SequencedDisabledAutomation(),
        refresh_fn=lambda _r, _repo: None,
    )
    assert calls == [1, 2]
    assert r["status"] == "COMPLETE"
    assert r["issue_number"] == 2
    assert len(gh.comments) == 0
    assert r["result"]["publication_record"]["state"] == "PREPARED"


def test_process_matches_accepts_current_executable_and_exact_argv(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    expected = (
        f"{Path(sys.executable).resolve()} -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )
    assert service_module._process_matches(expected, config) is True


def test_process_matches_accepts_equivalent_macos_framework_app_executable(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    simulated_bin = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/bin/python3.14"
    )
    simulated_app = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python"
    )

    monkeypatch.setattr(sys, "executable", str(simulated_bin))
    orig_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, *args, **kwargs: (
            self
            if "Frameworks/Python.framework" in str(self)
            else orig_resolve(self, *args, **kwargs)
        ),
    )

    cmd_bin = f"{simulated_bin} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"
    cmd_app = f"{simulated_app} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"

    assert service_module._process_matches(cmd_bin, config) is True
    assert service_module._process_matches(cmd_app, config) is True


def test_process_matches_rejects_arbitrary_or_unrelated_interpreter(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    simulated_bin = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/bin/python3.14"
    )
    monkeypatch.setattr(sys, "executable", str(simulated_bin))
    orig_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, *args, **kwargs: (
            self
            if "Frameworks/Python.framework" in str(self)
            else orig_resolve(self, *args, **kwargs)
        ),
    )

    unrelated_app = "/opt/homebrew/Cellar/python@3.13/3.13.0/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python"
    unrelated_bin = "/usr/local/bin/python3"
    fake_app = "/tmp/fake/Resources/Python.app/Contents/MacOS/Python"

    for bad_exe in (unrelated_app, unrelated_bin, fake_app):
        cmd = f"{bad_exe} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"
        assert service_module._process_matches(cmd, config) is False


def test_process_matches_rejects_wrong_config_or_extra_arguments(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    other_config = tmp_path / "other_config.json"
    other_config.write_text("{}", encoding="utf-8")

    current_exe = Path(sys.executable).resolve()
    wrong_config_cmd = (
        f"{current_exe} -m scripts.ops.external_intelligence_service daemon "
        f"--config {other_config.resolve()}"
    )
    assert service_module._process_matches(wrong_config_cmd, config) is False

    extra_arg_cmd = (
        f"{current_exe} -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()} --verbose"
    )
    assert service_module._process_matches(extra_arg_cmd, config) is False

    missing_arg_cmd = f"{current_exe} -m scripts.ops.external_intelligence_service daemon"
    assert service_module._process_matches(missing_arg_cmd, config) is False


def test_process_matches_rejects_malformed_command(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    malformed_cmd = f'{sys.executable} -m "unclosed quote'
    assert service_module._process_matches(malformed_cmd, config) is False


def test_process_matches_preserves_exact_executable_behavior_on_non_framework_layout(
    tmp_path, monkeypatch
):
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    simulated_bin = Path("/usr/bin/python3")
    monkeypatch.setattr(sys, "executable", str(simulated_bin))
    orig_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, *args, **kwargs: (
            self if str(self) == "/usr/bin/python3" else orig_resolve(self, *args, **kwargs)
        ),
    )

    matching_cmd = (
        f"/usr/bin/python3 -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )
    app_cmd = (
        f"/usr/Resources/Python.app/Contents/MacOS/Python -m scripts.ops.external_intelligence_service daemon "
        f"--config {config.resolve()}"
    )

    assert service_module._process_matches(matching_cmd, config) is True
    assert service_module._process_matches(app_cmd, config) is False


def test_service_status_accepts_macos_framework_python_app_process(tmp_path):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    source_sha = hashlib.sha256(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scripts/ops/external_intelligence_service.py")
        .read_bytes()
    ).hexdigest()
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    write_service_receipt(
        receipt,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 41257,
            "source_path": str(
                Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
            ),
            "source_sha256": source_sha,
            "config_path": str(config.resolve()),
            "config_sha256": config_sha,
            "started_at": 99.0,
            "heartbeat_at": 100.0,
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
            "last_error": None,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 41257\nlast exit code = (never exited)\n", ""
        )

    current_exe = Path(sys.executable).resolve()
    framework_root = current_exe.parent.parent
    app_exe = framework_root / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    proc_exe = app_exe if app_exe.is_file() else current_exe
    command = f"{proc_exe} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"

    result = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(41257, command)],
        now=100.5,
        receipt_path=receipt,
    )
    assert result["status"] == ServiceReadiness.READY.value
    assert result["ready"] is True


def test_service_status_duplicate_detection_fails_closed_across_bin_and_app(tmp_path, monkeypatch):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    source_sha = hashlib.sha256(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scripts/ops/external_intelligence_service.py")
        .read_bytes()
    ).hexdigest()
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    write_service_receipt(
        receipt,
        {
            "schema": "nexus.external_intelligence_daemon_receipt.v1",
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_path": str(
                Path(__file__).resolve().parents[2] / "scripts/ops/external_intelligence_service.py"
            ),
            "source_sha256": source_sha,
            "config_path": str(config.resolve()),
            "config_sha256": config_sha,
            "started_at": 99.0,
            "heartbeat_at": 100.0,
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
            "last_error": None,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    simulated_bin = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/bin/python3.14"
    )
    simulated_app = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python"
    )
    monkeypatch.setattr(sys, "executable", str(simulated_bin))
    orig_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, *args, **kwargs: (
            self
            if "Frameworks/Python.framework" in str(self)
            else orig_resolve(self, *args, **kwargs)
        ),
    )

    cmd1 = f"{simulated_bin} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"
    cmd2 = f"{simulated_app} -m scripts.ops.external_intelligence_service daemon --config {config.resolve()}"

    result = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, cmd1), (456, cmd2)],
        now=100.5,
        receipt_path=receipt,
    )
    assert result["status"] == ServiceReadiness.DUPLICATE_PROCESS.value
    assert result["ready"] is False
