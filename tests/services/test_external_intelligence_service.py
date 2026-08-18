from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts.ops.external_intelligence_service import (
    READINESS_SUCCESS_THRESHOLD,
    ServiceConfig,
    ServiceError,
    ServiceReadiness,
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
    def __init__(self, issues):
        self.issues = issues
        self.comments = []
        self.calls = []

    def list_open_labeled(self, repository, label):
        self.calls.append((repository, label))
        return list(self.issues.get(repository, []))

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


def _complete(reuse=False):
    return {
        "state": "COMPLETE",
        "reuse": reuse,
        "publication": {
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
            "status": ServiceReadiness.STARTING.value,
            "run_id": "run-1",
            "pid": 123,
            "source_sha256": "a" * 64,
            "config_sha256": "b" * 64,
            "heartbeat_at": 100.0,
            "successful_polls": 1,
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
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_sha256": source_sha,
            "config_sha256": config_sha,
            "heartbeat_at": 100.0,
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    good = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [
            (123, "python -m scripts.ops.external_intelligence_service daemon")
        ],
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
        process_snapshot=lambda: [
            (123, "python -m scripts.ops.external_intelligence_service daemon")
        ],
        now=100.5,
        receipt_path=receipt,
    )
    assert bad_exit["status"] == ServiceReadiness.DEGRADED.value

    stale = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [
            (123, "python -m scripts.ops.external_intelligence_service daemon")
        ],
        now=100.0 + 10_000,
        receipt_path=receipt,
    )
    assert stale["status"] == ServiceReadiness.STALE.value


def test_service_status_rejects_identity_mismatch_and_duplicate_processes(tmp_path):
    config = _config_file(tmp_path)
    receipt = tmp_path / "state" / "service" / "daemon.json"
    write_service_receipt(
        receipt,
        {
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_sha256": "wrong",
            "config_sha256": "wrong",
            "heartbeat_at": time.time(),
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
        },
    )

    def launchctl(*_args):
        return subprocess.CompletedProcess(
            ["launchctl"], 0, "state = running\npid = 123\nlast exit code = 0\n", ""
        )

    mismatch = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, "daemon")],
        receipt_path=receipt,
    )
    assert mismatch["status"] == ServiceReadiness.IDENTITY_MISMATCH.value
    write_service_receipt(
        receipt,
        {
            "status": ServiceReadiness.READY.value,
            "run_id": "run-1",
            "pid": 123,
            "source_sha256": mismatch["source_sha256"],
            "config_sha256": mismatch["config_sha256"],
            "heartbeat_at": time.time(),
            "successful_polls": READINESS_SUCCESS_THRESHOLD,
        },
    )
    duplicate = service_status(
        config,
        launchctl_runner=launchctl,
        process_snapshot=lambda: [(123, "daemon"), (456, "daemon")],
        receipt_path=receipt,
    )
    assert duplicate["status"] == ServiceReadiness.DUPLICATE_PROCESS.value


def test_render_comment_contains_only_compact_fields():
    result = _complete()
    result["raw_prompt"] = "SECRET_PROMPT"
    result["envelope"] = {"secret": "SECRET_ENVELOPE"}
    body = render_comment(result)
    assert "SECRET_PROMPT" not in body
    assert "SECRET_ENVELOPE" not in body
    assert "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE" in body
