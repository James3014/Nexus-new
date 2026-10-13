"""Wiring fixes batch 1 (#1862): request inputs reach research/memory/autoreason/ddtree/hyper/xray/sensor."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import (
    _exec_ddtree,
    _exec_memory,
    _exec_research,
    get_executor,
)
from nexus.engine.capability_receipts import (
    attested_receipt_dict,
    build_attested_trace_receipts,
    evaluate_receipt_claim_boundary,
)
from nexus.services.capability_registry import SKIP_REASONS, build_real_executor_invoker

FIXTURES = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures"
ORACLE = "\n\nNexus route oracle contract:\n- Expected capability receipts: memory."


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


# 1. research ---------------------------------------------------------------------------------


def test_research_task_statement_reaches_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.engine.phases.research import ResearchPhaseHandler

    monkeypatch.chdir(tmp_path)
    question = (_fixture(tmp_path, "research") / "question.md").read_text(encoding="utf-8").strip()
    seen: list[str] = []

    def fake_external(self: Any, query: str) -> dict[str, Any]:
        seen.append(query)
        return {
            "findings": [f"answer for: {query}"],
            "source": "test",
            "status": "SUCCESS",
            "tokens_used": 1,
        }

    monkeypatch.setattr(ResearchPhaseHandler, "_run_external_research", fake_external)
    monkeypatch.setattr(ResearchPhaseHandler, "_get_lancedb", lambda self: None)
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="research-1",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path)},
    )
    receipt = _exec_research(plan, question)
    findings = receipt.outcome["result"]["findings"]
    assert findings != ["Empty research task."]
    assert seen and question in seen[0]
    assert "compute_total" in findings[0]
    assert receipt.gate_passed is True
    # per-task run dir under the workspace, not a shared /tmp cache
    assert (tmp_path / ".nexus" / "research" / "research-1" / "researchpack.json").is_file()


def test_research_empty_statement_fails_closed(tmp_path: Path) -> None:
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="research-2",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path)},
    )
    receipt = _exec_research(plan, "")
    assert receipt.gate_passed is False


# 2. memory -----------------------------------------------------------------------------------


def _seed_memory(root: Path) -> None:
    from nexus.core.memory_manager import ProjectMemoryManager

    manager = ProjectMemoryManager(root)
    for item in json.loads((FIXTURES / "memory" / "insights.json").read_text(encoding="utf-8")):
        manager.add_insight(item["topic"], item["content"], item.get("insight_type", "RCA"))


def test_memory_finds_seeded_insight_from_task_statement(tmp_path: Path) -> None:
    _seed_memory(tmp_path)
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="mem-1",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path)},
    )
    receipt = _exec_memory(plan, "Recall the refund window insight" + ORACLE)
    assert receipt.outcome["search_performed"] is True
    assert receipt.outcome["hit_count"] >= 1


def test_memory_query_from_codeintel_and_negative_control(tmp_path: Path) -> None:
    _seed_memory(tmp_path)
    ctx = {
        "task_statement": "Recall the refund window insight",
        "route": {"workspace_root": str(tmp_path)},
    }
    hit = _invoke("memory", {**ctx, "codeintel": {"memory_query": "refund"}})
    miss = _invoke("memory", {**ctx, "codeintel": {"memory_query": "zzzqqq-nonexistent"}})
    assert _outcome(hit)["hit_count"] == 1
    assert _outcome(miss)["hit_count"] == 0
    assert _outcome(miss)["search_performed"] is True


def test_memory_blocks_on_empty_query(tmp_path: Path) -> None:
    plan = CapabilityExecutionPlan(
        plan_id="p", task_id="mem-2", phases=["R"], constraints={"workspace_root": str(tmp_path)}
    )
    receipt = _exec_memory(plan, "   ")
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == "PROJECT_MEMORY_CONTEXT_REQUIRED"


# 3. autoreason / ddtree ----------------------------------------------------------------------


def test_autoreason_ranks_request_candidate_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = json.loads((FIXTURES / "autoreason" / "candidates.json").read_text(encoding="utf-8"))
    result = _invoke(
        "autoreason", {"task_statement": "pick", "codeintel": {"autoreason_candidates": pool}}
    )
    assert result["gate_passed"] is True
    borda = _outcome(result)["result"]["borda_scores"]
    assert set(borda) == {"A", "B", "C"}
    assert len(set(borda.values())) > 1
    assert "c0" not in borda


def test_autoreason_without_pool_skips_no_candidate_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    result = _invoke("autoreason", {"task_statement": "pick", "codeintel": {}})
    assert result["skipped"] is True
    assert result["skip_reason"] == "no_candidate_pool"
    assert "no_candidate_pool" in SKIP_REASONS
    assert result["gate_passed"] is False
    assert result["outcome_contributed"] is False


def test_ddtree_prunes_request_candidate_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = json.loads((FIXTURES / "ddtree" / "candidates.json").read_text(encoding="utf-8"))
    result = _invoke(
        "ddtree",
        {
            "task_statement": "prune",
            "codeintel": {"ddtree_candidates": pool, "ddtree_max_candidates": 3},
        },
    )
    stats = _outcome(result)["result"]["tree_stats"]
    assert result["gate_passed"] is True
    assert stats["branch_count"] == 5
    assert stats["pruned_count"] == 2


def test_ddtree_without_pool_skips_and_never_fabricates_c0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    plan = CapabilityExecutionPlan(plan_id="p", task_id="dd-1", phases=["R"], constraints={})
    receipt = _exec_ddtree(plan, "prune")
    assert receipt.invoked is False
    assert receipt.outcome["skip_reason"] == "no_candidate_pool"
    assert "c0" not in json.dumps(receipt.outcome)


# 4. hyper ------------------------------------------------------------------------------------


def test_hyper_takes_config_from_request_and_meets_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    ws = _fixture(tmp_path, "hyper")
    (ws / "docs").mkdir()
    (ws / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")
    monkeypatch.chdir(ws)
    seen: dict[str, Any] = {}

    class _Result:
        status = "SUCCESS"
        attempt_count = 3

    def fake_run(*, repo_root: Path, config: Any) -> _Result:
        seen["root"], seen["cfg"] = repo_root, config
        return _Result()

    monkeypatch.setattr(sprint, "run_hyper_sprint", fake_run)
    result = _invoke(
        "hyper",
        {
            "task_statement": "Improve README wording",
            "codeintel": {
                "workspace_root": str(ws),
                "hyper_candidate_count": 4,
                "hyper_target_file": "docs/notes.md",
                "hyper_llm_mode": True,
            },
        },
    )
    cfg = seen["cfg"]
    assert (cfg.candidate_count, cfg.target_file, cfg.llm_mode) == (4, "docs/notes.md", True)
    assert seen["root"] == ws.resolve()
    assert result["status"] == "SUCCEEDED"
    assert "contract_violations" not in result["response"]
    outcome = _outcome(result)
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert outcome["evidence_refs"]


def test_hyper_defaults_stay_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    (tmp_path / "README.md").write_text("r\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    seen: dict[str, Any] = {}

    class _Result:
        status = "FAILED"
        attempt_count = 1

    def fake_run(*, repo_root: Path, config: Any) -> _Result:
        seen["cfg"] = config
        return _Result()

    monkeypatch.setattr(sprint, "run_hyper_sprint", fake_run)
    result = _invoke(
        "hyper", {"task_statement": "x", "codeintel": {"workspace_root": str(tmp_path)}}
    )
    assert (seen["cfg"].candidate_count, seen["cfg"].llm_mode) == (1, False)
    assert result["gate_passed"] is False


# 5. xray -------------------------------------------------------------------------------------


def test_xray_scans_request_target_not_hard_coded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)  # xray writes .nexus/runtime/<task> relative to cwd
    (ws / "other_module.py").write_text(
        "def other_symbol_unique():\n    return 1\n", encoding="utf-8"
    )
    result = _invoke(
        "xray",
        {
            "task_statement": "scan",
            "task_id": "xray-1",
            "codeintel": {"workspace_root": str(ws), "xray_targets": ["other_module.py"]},
        },
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is True
    assert outcome["scan_targets"] == [str(ws / "other_module.py")]
    reports = list(ws.glob(".nexus/runtime/*/xray_report_full.md"))
    assert reports and "other_symbol_unique" in reports[0].read_text(encoding="utf-8")


def test_xray_missing_request_target_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _invoke(
        "xray",
        {
            "task_statement": "scan",
            "codeintel": {"workspace_root": str(tmp_path), "xray_targets": ["missing.py"]},
        },
    )
    assert result["gate_passed"] is False


# 6. harness_preflight_sensor -----------------------------------------------------------------


def _sensor(planner: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        "harness_preflight_sensor",
        {
            "task_statement": "check",
            "task_type": "repair",
            "planner": planner,
            "codeintel": {"verify_commands": ["true"]},
        },
    )


def test_sensor_receives_selected_capabilities_from_planner_stage() -> None:
    result = _sensor({
        "selected_capabilities": ["harness_preflight_sensor", "pregate"],
        "pending_capabilities": [],
    })
    outcome = _outcome(result)
    assert outcome["selected_capabilities"] == ["harness_preflight_sensor", "pregate"]
    assert result["gate_passed"] is True


def test_sensor_can_fail_on_pending_capabilities() -> None:
    result = _sensor({
        "selected_capabilities": ["harness_preflight_sensor", "hyper"],
        "pending_capabilities": ["hyper"],
    })
    outcome = _outcome(result)
    assert outcome["pending_capabilities"] == ["hyper"]
    assert result["gate_passed"] is False


# 7. receipt attestation ----------------------------------------------------------------------


def test_executor_receipt_with_evidence_is_not_simulated(tmp_path: Path) -> None:
    _seed_memory(tmp_path)
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="att-1",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path), "memory_query": "refund"},
    )
    receipt = get_executor("memory")(plan, "refund")
    raw = receipt.to_dict()
    # nexus-runtime #187: the runtime itself now derives ``simulated`` from evidence.
    assert raw["receipt_base"]["claim_boundary"]["simulated"] is False
    attested = attested_receipt_dict(receipt)
    boundary = attested["receipt_base"]["claim_boundary"]
    assert boundary["simulated"] is False
    assert boundary["receipt_present"] is True
    assert boundary["public_claim_allowed"] is False
    # The runtime projection is authoritative; Nexus-new no longer re-projects it.
    assert attested["receipt_base"]["receipt_hash"] == raw["receipt_base"]["receipt_hash"]
    assert "receipt_base_attestation_error" not in attested


def test_auth_block_and_skip_stay_simulated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    plan = CapabilityExecutionPlan(plan_id="p", task_id="att-2", phases=["R"], constraints={})
    blocked = get_executor("ddtree")(plan, "x")
    assert evaluate_receipt_claim_boundary(blocked).simulated is True
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    skipped = get_executor("ddtree")(plan, "x")
    assert evaluate_receipt_claim_boundary(skipped).simulated is True


def test_trace_receipts_without_executor_outcome_stay_simulated() -> None:
    plan = {"selected_capabilities": ["memory"], "pending_capabilities": []}
    plain = build_attested_trace_receipts(plan=plan)
    assert plain[0]["receipt_base"]["claim_boundary"]["simulated"] is True
    attested = build_attested_trace_receipts(
        plan=plan, executor_outcomes={"memory": {"action": "search", "evidence_refs": ["ev_x"]}}
    )
    # engine receipt was never invoked, so even a reported outcome cannot flip simulated
    assert attested[0]["receipt_base"]["claim_boundary"]["simulated"] is True


# 8. containment and authorization (security review on #1870) -------------------------------


def _blocked_reason(result: dict[str, Any]) -> str:
    return str(_outcome(result).get("error") or result["response"].get("error") or "")


@pytest.mark.parametrize("escape", ["../outside.txt", "ABS"])
def test_xray_rejects_targets_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, escape: str
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("def secret():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(ws)
    target = str(outside) if escape == "ABS" else escape
    result = _invoke("xray", {"task_statement": "scan", "codeintel": {"xray_targets": [target]}})
    assert result["gate_passed"] is False
    assert _blocked_reason(result) == "path_outside_workspace"
    assert not list(ws.glob(".nexus/runtime/*/xray_report_full.md"))


def test_xray_ignores_workspace_root_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "elsewhere.py").write_text(
        "def elsewhere_symbol():\n    return 1\n", encoding="utf-8"
    )
    monkeypatch.chdir(ws)
    result = _invoke(
        "xray",
        {
            "task_statement": "scan",
            "codeintel": {"workspace_root": str(tmp_path), "xray_targets": ["elsewhere.py"]},
        },
    )
    # the request root is ignored, so the target is looked up under the project root only
    assert result["gate_passed"] is False
    assert _blocked_reason(result) == "path_outside_workspace"


@pytest.mark.parametrize("key", ["hyper_target_file", "hyper_test_file"])
@pytest.mark.parametrize("escape", ["../outside.py", "ABS"])
def test_hyper_rejects_files_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, escape: str
) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("r\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(ws)
    called: list[Any] = []
    monkeypatch.setattr(sprint, "run_hyper_sprint", lambda **kw: called.append(kw))
    value = str(outside) if escape == "ABS" else escape
    result = _invoke("hyper", {"task_statement": "x", "codeintel": {key: value}})
    assert result["gate_passed"] is False
    assert _blocked_reason(result) == "path_outside_workspace"
    assert not called


def test_hyper_ignores_workspace_root_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("r\n", encoding="utf-8")
    monkeypatch.chdir(ws)
    seen: dict[str, Any] = {}

    class _R:
        status = "FAILED"
        attempt_count = 1

    def fake(*, repo_root: Path, config: Any) -> _R:
        seen["root"] = repo_root
        return _R()

    monkeypatch.setattr(sprint, "run_hyper_sprint", fake)
    _invoke("hyper", {"task_statement": "x", "codeintel": {"workspace_root": str(tmp_path)}})
    assert seen["root"] == ws.resolve()


def test_hyper_llm_mode_flag_is_not_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")  # passes the executor-level gate
    (tmp_path / "README.md").write_text("r\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    called: list[Any] = []
    monkeypatch.setattr(sprint, "run_hyper_sprint", lambda **kw: called.append(kw))
    result = _invoke("hyper", {"task_statement": "x", "codeintel": {"hyper_llm_mode": True}})
    assert result["gate_passed"] is False
    assert "BLOCKED_EXTERNAL_AUTH" in _blocked_reason(result)
    assert not called


def test_hyper_still_requires_provider_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", raising=False)
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    result = _invoke("hyper", {"task_statement": "x", "codeintel": {"hyper_llm_mode": True}})
    assert result["gate_passed"] is False
    assert "BLOCKED_EXTERNAL_AUTH" in _blocked_reason(result)


@pytest.mark.parametrize("name", ["autoreason", "ddtree"])
def test_pool_executors_ignore_constraint_authorization_flag(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    pool = [{"candidate_id": "A", "text": "a", "score": 1.0, "evidence_refs": []}]
    result = _invoke(
        name,
        {
            "task_statement": "x",
            "allow_fixture_model_boundary": True,
            "codeintel": {"candidate_pool": pool, "allow_fixture_model_boundary": True},
        },
    )
    assert result["gate_passed"] is False
    assert "BLOCKED_EXTERNAL_AUTH" in _blocked_reason(result)


def test_research_ignores_request_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.engine.phases.research import ResearchPhaseHandler

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.setattr(
        ResearchPhaseHandler,
        "_run_external_research",
        lambda self, q: {"findings": ["x"], "source": "t", "status": "SUCCESS", "tokens_used": 1},
    )
    monkeypatch.setattr(ResearchPhaseHandler, "_get_lancedb", lambda self: None)
    for root in (str(tmp_path), "../"):
        _invoke(
            "research",
            {
                "task_id": "research-esc",
                "task_statement": "question",
                "codeintel": {"workspace_root": root},
            },
        )
    assert not (tmp_path / ".nexus").exists()
    assert (ws / ".nexus" / "research" / "research-esc").is_dir()


# 9. research egress gate and request URLs (security review on #1870) ------------------------


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import socket
    import subprocess
    import urllib.request

    calls: list[str] = []

    def boom(*args: Any, **kwargs: Any) -> Any:
        calls.append(repr(args)[:80])
        raise AssertionError("network or subprocess egress attempted")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    return calls


def _real_research_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.engine.phases.research import ResearchPhaseHandler

    monkeypatch.setattr(
        ResearchPhaseHandler,
        "_run_external_research",
        ResearchPhaseHandler._real_run_external_research,  # type: ignore[attr-defined]
    )


def test_research_unauthorized_makes_no_outbound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.chdir(tmp_path)
    _real_research_provider(monkeypatch)
    calls = _forbid_network(monkeypatch)
    result = _invoke(
        "research",
        {
            "task_id": "r-auth",
            "task_statement": "look at https://example.invalid/x and explain compute_total",
            "codeintel": {
                "provider_url": "http://169.254.169.254/latest",
                "research_url": "http://x.invalid",
            },
        },
    )
    assert result["gate_passed"] is False
    assert _blocked_reason(result) == "BLOCKED_EXTERNAL_AUTH"
    assert _outcome(result)["provider_call_count"] == 0
    assert calls == []


HOSTILE_TASKS = [
    "fetch http://169.254.169.254/latest/meta-data and explain compute_total",
    "read file:///etc/passwd then answer",
    "see //evil.invalid/path and answer",
    "HTTP://EVIL.INVALID/%2e%2e/%2e%2e/etc/passwd answer",
    "http://evil\u3002invalid/ http://\uff45vil.invalid/ http%3A%2F%2Fevil.invalid%2F answer",
    "www.evil.invalid/x ftp://evil.invalid/y answer",
]


@pytest.mark.parametrize("task", HOSTILE_TASKS)
def test_research_authorized_task_text_is_opaque_payload_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task: str
) -> None:
    import socket
    import urllib.request

    from nexus.engine.phases.research import ResearchPhaseHandler
    from nexus.services.reach.ucc_router import UCCRouter

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.chdir(tmp_path)
    _real_research_provider(monkeypatch)
    queries: list[str] = []
    fetched: list[str] = []

    def fake_chub(self: Any, query: str) -> dict[str, Any]:
        queries.append(query)
        return {"findings": ["ok"], "source": "chub", "status": "SUCCESS", "tokens_used": 1}

    def forbid(*args: Any, **kwargs: Any) -> Any:
        fetched.append(repr(args)[:80])
        raise AssertionError("request-derived fetch attempted")

    monkeypatch.setattr(ResearchPhaseHandler, "_run_chub", fake_chub)
    monkeypatch.setattr(UCCRouter, "reach", forbid)
    monkeypatch.setattr(socket, "create_connection", forbid)
    monkeypatch.setattr(urllib.request, "urlopen", forbid)
    result = _invoke(
        "research",
        {
            "task_id": "r-url",
            "task_statement": task,
            "codeintel": {"provider_url": "http://169.254.169.254/"},
        },
    )
    assert result["gate_passed"] is True
    assert fetched == []
    # exactly one provider call, with the task only as the opaque query string
    assert len(queries) == 1 and task in queries[0] and "provider_url" not in queries[0]
    assert not (Path.home() / ".openclaw" / "memory" / "lancedb-research" / "r-url").exists()


@pytest.mark.parametrize("task", HOSTILE_TASKS)
def test_research_unauthorized_hostile_task_is_blocked_without_egress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task: str
) -> None:
    from nexus.services.reach.ucc_router import UCCRouter

    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.chdir(tmp_path)
    _real_research_provider(monkeypatch)
    calls = _forbid_network(monkeypatch)
    monkeypatch.setattr(UCCRouter, "reach", lambda self, url: calls.append(url))
    result = _invoke("research", {"task_id": "r-hostile", "task_statement": task})
    assert _blocked_reason(result) == "BLOCKED_EXTERNAL_AUTH"
    assert _outcome(result)["provider_call_count"] == 0
    assert calls == []


def test_executor_outcome_only_tightens_runtime_boundary(tmp_path: Path) -> None:
    _seed_memory(tmp_path)
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="att-3",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path), "memory_query": "refund"},
    )
    receipt = get_executor("memory")(plan, "refund")
    assert receipt.to_dict()["receipt_base"]["claim_boundary"]["simulated"] is False
    # an outcome revealing a non-execution flips simulated to true ...
    tightened = attested_receipt_dict(receipt, {"action": "skip", "skipped": True})
    assert tightened["receipt_base"]["claim_boundary"]["simulated"] is True
    assert tightened["receipt_base"]["claim_boundary"]["claim_eligible"] is False
    # (never loosening a runtime simulated=true receipt is covered by
    # test_trace_receipts_without_executor_outcome_stay_simulated)


class _FakeRuntimeReceipt:
    """A receipt whose runtime projection carries a chosen ``simulated`` value."""

    name = "memory"
    selected = True
    invoked = True
    gate_passed = True
    outcome_contributed = True
    evidence_present = True
    executor_id = "capability_executor_registry:memory"
    evidence_refs = ("ev_fake",)
    failure_reason = ""
    telemetries: dict[str, Any] = {}
    outcome: dict[str, Any] = {"action": "search", "evidence_refs": ["ev_fake"]}

    def __init__(self, cb: dict[str, Any] | None) -> None:
        self._cb = cb

    def to_dict(self) -> dict[str, Any]:
        rb: dict[str, Any] = {"source_world": "B", "consumption_chain": [{"consumer": "engine"}]}
        if self._cb is not None:
            rb["claim_boundary"] = dict(self._cb)
        return {"name": self.name, "receipt_base": rb}


def test_runtime_simulated_true_cannot_be_flipped_by_nexus_new() -> None:
    receipt = _FakeRuntimeReceipt({"simulated": True, "claim_eligible": False})
    for outcome in (None, {"action": "search", "evidence_refs": ["ev_x", "ev_y"]}):
        attested = attested_receipt_dict(receipt, outcome)
        assert attested["receipt_base"]["claim_boundary"]["simulated"] is True
        assert attested["receipt_base"]["claim_boundary"]["claim_eligible"] is False
        assert attested == receipt.to_dict()  # no state drift from the runtime projection


@pytest.mark.parametrize(
    "cb", [None, {}, {"simulated": None}, {"simulated": "false"}, {"simulated": 0}]
)
def test_missing_or_non_bool_simulated_is_treated_as_simulated(cb: dict[str, Any] | None) -> None:
    attested = attested_receipt_dict(_FakeRuntimeReceipt(cb))
    boundary = attested["receipt_base"]["claim_boundary"]
    assert boundary["simulated"] is True
    assert boundary["claim_eligible"] is False
    assert boundary["public_claim_allowed"] is False


def test_audit_reads_missing_or_non_bool_simulated_as_simulated() -> None:
    import importlib

    audit = importlib.import_module("scripts.ops.capability_wiring_audit")
    for value in (None, "false", 0):
        obs = audit.Obs(
            source="t",
            stage={},
            resp={},
            outcome={},
            row={"claim_boundary": {"simulated": value}},
            receipt_terminal="",
            receipt_failure_class="",
            admission={},
            executor_receipt={},
            receipt={},
        )
        assert audit.claim_boundary_simulated(obs, {})[0] is True
