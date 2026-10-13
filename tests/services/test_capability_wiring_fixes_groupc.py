"""Wiring fixes group C: hyper local channel, committee proposer_id + execution verifier, swarm run."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.committee.execution_verifier import NOT_EXECUTED_NO_BARRIER
from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services.capability_registry import build_real_executor_invoker

FIXTURES = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures"


def _fixture(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURES / name, dest)
    return dest


def _invoke(name: str, context: dict[str, Any]) -> dict[str, Any]:
    invoker = build_real_executor_invoker(name)
    assert invoker is not None
    return invoker({"task_id": f"t-{name}", **context})


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    return result["response"]["outcome"]


def _git_repo(path: Path) -> None:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run([*git, "add", "-A"], cwd=path, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], cwd=path, check=True)


# hyper ----------------------------------------------------------------------------------------


def test_hyper_forwards_local_channel_and_min_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    ws = _fixture(tmp_path, "hyper")
    monkeypatch.chdir(ws)
    seen: dict[str, Any] = {}

    class _Cand:
        def __init__(self, source: str, score: float, error: str = "") -> None:
            self.seed, self.source, self.score, self.error = 0, source, score, error
            self.candidate_code = "x"

    class _Result:
        status = "SUCCESS"
        attempt_count = 2
        model_calls = 6
        candidates = [_Cand("llm_local_armor", 1.0), _Cand("local", 0.4, "pytest_failed")]
        learning_trace = {"llm_mode_effective": True, "learn_slo_guard": {"active": False}}
        unified_runtime_receipts: list[dict[str, Any]] = []

    def fake_run(*, repo_root: Path, config: Any) -> _Result:
        seen["cfg"] = config
        return _Result()

    monkeypatch.setattr(sprint, "run_hyper_sprint", fake_run)
    result = _invoke(
        "hyper",
        {
            "task_statement": "fix pricing",
            "codeintel": {
                "workspace_root": str(ws),
                "hyper_target_file": "pricing.py",
                "hyper_test_file": "test_pricing.py",
                "hyper_candidate_count": 3,
                "hyper_min_candidate_pool": 2,
                "hyper_llm_mode": True,
                "hyper_llm_channel": "local",
            },
        },
    )
    cfg = seen["cfg"]
    assert (cfg.llm_channel, cfg.min_candidate_pool, cfg.test_file) == (
        "local",
        2,
        "test_pricing.py",
    )
    assert result["gate_passed"] is True
    outcome = _outcome(result)
    assert outcome["model_verified_candidate_count"] == 1
    # A rejected candidate is reported as "rejection", which must not fail the whole receipt.
    assert outcome["candidates"][1]["rejection"] == "pytest_failed"


def test_hyper_rejects_unknown_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    ws = _fixture(tmp_path, "hyper")
    monkeypatch.chdir(ws)
    called: list[Any] = []
    monkeypatch.setattr(sprint, "run_hyper_sprint", lambda **kw: called.append(kw))
    result = _invoke(
        "hyper",
        {
            "task_statement": "x",
            "codeintel": {"workspace_root": str(ws), "hyper_llm_channel": "elsewhere"},
        },
    )
    assert not called
    assert result["gate_passed"] is False


@pytest.mark.parametrize(
    ("env", "test_file", "category"),
    [
        ({}, "test_pricing.py", "local_model_unbound"),
        (
            {"NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder:7b-instruct"},
            None,
            "local_channel_requires_test_file",
        ),
        (
            {"NEXUS_LOCAL_MODEL_NAME": "not-a-registered-model:1b"},
            "test_pricing.py",
            "local_worker_not_registered",
        ),
    ],
)
def test_local_armor_generator_fails_closed_without_calling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    test_file: str | None,
    category: str,
) -> None:
    from nexus.research.sprint_service import LLMCandidateError, LocalArmorCandidateGenerator

    for name in ("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", "NEXUS_LOCAL_MODEL_NAME"):
        monkeypatch.delenv(name, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    ws = _fixture(tmp_path, "hyper")
    gen = LocalArmorCandidateGenerator(ws, target_file="pricing.py", test_file=test_file)
    with pytest.raises(LLMCandidateError) as err:
        gen.generate(source_code="", task="t", mutation_hint="", seed=0)
    assert str(err.value) == category
    assert err.value.metadata["model_calls"] == 0


# committee ------------------------------------------------------------------------------------


def _committee_context(ws: Path, proposals: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "task_statement": "pick a candidate",
        "route": {"workspace_root": str(ws)},
        "codeintel": {"committee_proposals": proposals, **extra},
    }


def test_committee_executes_candidates_and_picks_the_passing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    ws = _fixture(tmp_path, "committee")
    monkeypatch.chdir(ws)
    proposals = json.loads((ws / "proposals.json").read_text(encoding="utf-8"))
    before = (ws / "calc.py").read_bytes()
    result = _invoke(
        "committee",
        _committee_context(ws, proposals, committee_verify_commands=["python3 repro.py"]),
    )
    outcome = _outcome(result)
    if not os_sandbox_available():
        # No OS barrier (Linux CI): candidate code never runs, nobody is verified, no winner.
        assert outcome["winner_id"] == ""
        assert outcome["winner_proposer_id"] == ""
        assert [r["verify_result"] for r in outcome["execution_results"]] == [
            NOT_EXECUTED_NO_BARRIER
        ] * 3
        assert all(r["exit_codes"] == [] for r in outcome["execution_results"])
        assert (ws / "calc.py").read_bytes() == before
        return
    assert result["gate_passed"] is True
    assert outcome["winner_proposer_id"] == "wiring-proposer-a"
    assert [r["verify_result"] for r in outcome["execution_results"]] == ["pass", "fail", "fail"]
    assert all(Path(r["workspace"]).is_relative_to(ws) for r in outcome["execution_results"])
    assert (ws / "calc.py").read_bytes() == before


def test_committee_single_candidate_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    ws = _fixture(tmp_path, "committee")
    monkeypatch.chdir(ws)
    proposals = json.loads((ws / "proposals.json").read_text(encoding="utf-8"))[:1]
    result = _invoke("committee", _committee_context(ws, proposals))
    assert result["gate_passed"] is False
    assert _outcome(result)["error"] == "TWO_INDEPENDENT_CANDIDATES_REQUIRED"


def test_committee_without_verifier_records_no_verdict_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.verifiers.registry import VerifierRegistry

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(VerifierRegistry, "_registry", {})
    ws = _fixture(tmp_path, "committee")
    monkeypatch.chdir(ws)
    proposals = json.loads((ws / "proposals.json").read_text(encoding="utf-8"))
    result = _invoke("committee", _committee_context(ws, proposals))
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["verdict_count"] == 0
    assert outcome["error"] == "NO_COMMITTEE_VERIFIER_VERDICTS"


def test_committee_workspace_root_comes_from_route_not_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.core.capability_executor_registry as exe

    captured: dict[str, Any] = {}

    def fake_executor(plan: Any, task_desc: str) -> Any:
        captured.update(plan.constraints or {})
        raise RuntimeError("stop")

    monkeypatch.setitem(exe.EXECUTOR_REGISTRY, "committee", fake_executor)
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    route_root = tmp_path / "route-root"
    route_root.mkdir()
    invoker = build_real_executor_invoker("committee")
    assert invoker is not None
    invoker({
        "task_id": "t",
        "task_statement": "x",
        "route": {"workspace_root": str(route_root)},
        "codeintel": {"workspace_root": "/elsewhere", "committee_proposals": []},
    })
    assert captured.get("workspace_root") == str(route_root)


def test_canonical_context_still_rejects_model_keys_in_proposals() -> None:
    from nexus_runtime.support.contracts.canonical_execution import _freeze_json

    with pytest.raises(ValueError, match="route_override_forbidden"):
        _freeze_json({"committee_proposals": [{"model": "x"}]}, path="codeintel")
    frozen = _freeze_json({"committee_proposals": [{"proposer_id": "x"}]}, path="codeintel")
    assert frozen["committee_proposals"][0]["proposer_id"] == "x"


# swarm / multi_agent ----------------------------------------------------------------------------


def test_battle_swarm_cleanup_never_prunes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import nexus.engine.battle_swarm as bs

    calls: list[list[str]] = []
    monkeypatch.setattr(bs.subprocess, "run", lambda argv, **kw: calls.append(list(argv)))
    bs.BattleSwarm(project_root=str(tmp_path)).cleanup({
        "worktrees_to_clean": [tmp_path / "wt"],
        "branches_to_clean": ["b"],
    })
    assert calls and not any("prune" in argv for argv in calls)


def test_swarm_requires_target_and_verify_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.chdir(tmp_path)
    result = _invoke("swarm", {"task_statement": "x", "route": {"workspace_root": str(tmp_path)}})
    assert result["gate_passed"] is False
    assert _outcome(result)["error"] == "SWARM_TARGET_AND_VERIFY_SCRIPT_REQUIRED"


def test_swarm_foreign_lock_blocks_before_any_worktree(tmp_path: Path) -> None:
    from nexus.engine.swarm_run import run_bounded_swarm

    ws = _fixture(tmp_path, "swarm")
    _git_repo(ws)
    lock = ws / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"locks": {"calc.py": "other-task"}}), encoding="utf-8")
    report = run_bounded_swarm(
        workspace_root=ws, task_id="t1", task="fix", target_file="calc.py", verify_script="repro.py"
    )
    assert (report["status"], report["reason"]) == ("BLOCKED", "FILE_LOCK_CONFLICT")
    assert not (ws / ".nexus" / "runs").exists()


def test_swarm_runs_workers_in_worktrees_and_integration_refuses_without_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint
    from nexus.engine.swarm_run import run_bounded_swarm

    ws = _fixture(tmp_path, "swarm")
    _git_repo(ws)

    class _StubWorker:
        """Test stub for the local-model worker: writes the known fix (no model is called)."""

        def __init__(self, project_root: Path, **_kw: Any) -> None:
            self.root = Path(project_root)

        def generate(self, *, source_code: str, **_kw: Any) -> tuple[str, dict[str, Any]]:
            assert self.root != ws.resolve()  # runs inside a worktree, not the workspace
            return source_code.replace("a - b", "a + b"), {"model_calls": 0, "model_name": "stub"}

    monkeypatch.setattr(sprint, "LocalArmorCandidateGenerator", _StubWorker)
    state_dir = tmp_path / "self-hosted-state"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(state_dir))
    report = run_bounded_swarm(
        workspace_root=ws, task_id="t2", task="fix", target_file="calc.py", verify_script="repro.py"
    )
    assert (report["status"], report["reason"]) == (
        "BLOCKED",
        "INTEGRATION_OWNER_AUTHORITY_REQUIRED",
    )
    integration = report["integration"]
    assert integration["authority"].startswith(
        "nexus.orchestrator.self_hosted_task_service.SelfHostedTaskService.integrate_approved"
    )
    assert integration["attempted"] is True and integration["merge_performed"] is False
    assert integration["refusal"] == "unknown task_id: t2"
    assert integration["candidate_commit_sha"] == report["winner"]["commit"]
    assert report["winner"]["verify_result"] == "pass"
    assert len(report["workers"]) == 2
    for worker in report["workers"]:
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{worker['commit']}^{{commit}}"], cwd=ws
            ).returncode
            == 0
        )
    assert sorted(report["worktrees_removed"]) == sorted(report["worktrees"])
    assert report["lock"]["held_by_this_task"] is True and report["lock"]["released"] is True
    assert "a - b" in (ws / "calc.py").read_text(encoding="utf-8")
    branches = subprocess.run(
        ["git", "branch", "--list", "battle_*"], cwd=ws, capture_output=True, text=True
    ).stdout
    assert branches.strip() == ""
