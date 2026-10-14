"""P-CONTAM-01 on the canonical research path (#2199).

The contamination guard must run where the canonical research executor accepts research
output: contaminated output and guard errors are BLOCKed, clean output still passes.
These tests go through the registered executor invoker, not the guard alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from nexus.services.capability_registry import build_real_executor_invoker


def _run_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pack: dict[str, Any] | Callable[[str], dict[str, Any]],
    *,
    task_id: str,
    task: str = "How does compute_total apply the discount?",
) -> dict[str, Any]:
    from nexus.engine.phases.research import ResearchPhaseHandler

    def provider(self: Any, query: str) -> dict[str, Any]:
        return pack(query) if callable(pack) else dict(pack)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ResearchPhaseHandler, "_run_external_research", provider)
    monkeypatch.setattr(ResearchPhaseHandler, "_get_lancedb", lambda self: None)
    invoker = build_real_executor_invoker("research")
    assert invoker is not None
    return invoker({
        "task_id": task_id,
        "task_statement": task,
    })


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    return result["response"]["outcome"]


def _success(**extra: Any) -> dict[str, Any]:
    return {"source": "test", "status": "SUCCESS", "tokens_used": 1, **extra}


def test_canonical_research_blocks_design_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total applies the discount; recommend a patch plan to fix it"]),
        task_id="contam-lang",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert outcome["policy_id"] == "P-CONTAM-01"
    assert "patch plan" in outcome["detected_terms"]
    # the contaminated research output is not handed downstream in the receipt
    assert "result" not in outcome


def test_canonical_research_blocks_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], patch_plan="candidate_001"),
        task_id="contam-field",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["error"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert outcome["detected_terms"] == ["design_field"]


def test_canonical_research_blocks_nested_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], raw={"winner": "candidate_b"}),
        task_id="contam-raw",
    )
    assert result["gate_passed"] is False
    assert _outcome(result)["detected_terms"] == ["design_field"]


def test_canonical_research_clean_output_passes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = ["compute_total multiplies the subtotal by 0.9 when the discount flag is set"]
    result = _run_research(
        tmp_path, monkeypatch, _success(findings=findings), task_id="contam-clean"
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert outcome["action"] == "run"
    assert outcome["result"]["findings"] == findings
    assert "error" not in outcome


def test_canonical_research_guard_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research import contamination_guard

    def broken(payload: dict[str, Any]) -> Any:
        raise RuntimeError("guard exploded")

    monkeypatch.setattr(contamination_guard, "evaluate_research_contamination", broken)
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies the subtotal by 0.9"]),
        task_id="contam-err",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "RESEARCH_CONTAMINATION_GUARD_ERROR"
    assert "result" not in outcome


# --- #2216 review (Owner option A): phrase-level terms, echo stripping, full-pack scan ---


def test_canonical_research_normal_software_text_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = [
        "Release 2.3 includes a fix for the race in the websocket reconnect loop; the patch "
        "landed in commit a1b2c3 and changes the retry delay. See the change log.",
        "To modify the timeout, set NEXUS_RESEARCH_PROVIDER_TIMEOUT_SEC; the docs recommend 60 seconds.",
        "The library can implement backoff itself; the recommended setting is jitter=full.",
    ]
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=findings, summary="The fix shipped in 2.3."),
        task_id="fp-normal",
    )
    assert result["gate_passed"] is True
    assert _outcome(result)["semantic_status"] == "SUCCEEDED"


def test_canonical_research_echoed_query_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = "Find out whether the fix is to clamp totals in compute_total before rounding"

    def echoing(query: str) -> dict[str, Any]:
        return _success(
            findings=[f"Results for: {query}", "compute_total rounds after applying the discount."]
        )

    result = _run_research(tmp_path, monkeypatch, echoing, task_id="fp-echo", task=task)
    assert result["gate_passed"] is True


def test_canonical_research_echo_does_not_hide_other_contamination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = "Find out whether the fix is to clamp totals in compute_total before rounding"

    def echoing(query: str) -> dict[str, Any]:
        return _success(findings=[f"Results for: {query}", "We recommend replacing compute_total."])

    result = _run_research(tmp_path, monkeypatch, echoing, task_id="fp-echo-contam", task=task)
    assert result["gate_passed"] is False
    assert _outcome(result)["detected_terms"] == ["we recommend", "recommend replacing"]


def test_canonical_research_blocks_contaminated_blocked_assumptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(
            findings=["compute_total rounds half-up"],
            blocked_assumptions=["The fix is to round half-even."],
        ),
        task_id="contam-ba",
    )
    assert result["gate_passed"] is False
    assert _outcome(result)["error"] == "RESEARCH_CONTAMINATION_DETECTED"


def test_canonical_research_scans_findings_when_blocked_assumptions_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["Proposed patch: drop the rounding."], blocked_assumptions=["none"]),
        task_id="contam-ba-findings",
    )
    assert result["gate_passed"] is False
    assert _outcome(result)["detected_terms"] == ["proposed patch"]


@pytest.mark.parametrize(
    "extra",
    [
        {"summary": "Suggested fix: guard the division."},
        {"raw": {"answer": "I recommend changing compute_total."}},
        {"provider_notes": {"deep": ["Implementation plan: add a retry wrapper."]}},
    ],
    ids=["summary", "raw_answer", "non_schema_key"],
)
def test_canonical_research_blocks_contaminated_non_findings_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], **extra),
        task_id="contam-field-" + next(iter(extra)),
    )
    assert result["gate_passed"] is False
    assert _outcome(result)["error"] == "RESEARCH_CONTAMINATION_DETECTED"


def test_guard_terms_parameter_keeps_legacy_default() -> None:
    from nexus.research.contamination_enforcement import CANONICAL_DESIGN_TERMS
    from nexus.research.contamination_guard import evaluate_research_contamination

    payload = {"constraints": ["a fix for the race landed in 2.3"]}
    assert evaluate_research_contamination(payload).detected_terms == ("fix",)
    assert evaluate_research_contamination(payload, terms=CANONICAL_DESIGN_TERMS).passed is True
    cjk = {"constraints": ["根因在 parser；建議修改 parse() 的邊界判斷"]}
    assert evaluate_research_contamination(cjk, terms=CANONICAL_DESIGN_TERMS).detected_terms == (
        "建議修改",
    )


# --- research auto-flow (nexus/app/research_flow_service.py run_auto_flow) ---


def _run_auto_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, research_context: dict[str, Any]
) -> dict[str, Any]:
    from nexus.app import research_flow_service as rfs
    from nexus.research.sprint_service import SprintResult
    from tests.engine.test_research_auto_flow_guard_audit import (
        _patch_common_success,
        _write_task_files,
    )

    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)
    monkeypatch.setattr(
        rfs,
        "run_hyper_sprint",
        lambda *a, **k: SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["pytest", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        ),
    )
    real_refresh = rfs._refresh_route_for_runtime_candidate_factory

    def refresh_with_research(**kwargs: Any) -> dict[str, Any]:
        route = real_refresh(**kwargs)
        decision = dict(route.get("route_decision") or {})
        decision["selected_capabilities"] = [
            *list(decision.get("selected_capabilities") or []),
            "research",
        ]
        route["route_decision"] = decision
        route["research_context"] = research_context
        return route

    monkeypatch.setattr(rfs, "_refresh_route_for_runtime_candidate_factory", refresh_with_research)
    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="explain the websocket timeout race in demo.py",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )
    return payload["nexus_usage_trace"]["capabilities"]


def _flow_context(**extra: Any) -> dict[str, Any]:
    return {
        "schema": "nexus_research_context_v1",
        "role": "claim_scout",
        "hypothesis": "explain the websocket timeout race in demo.py",
        "recommended_capabilities": ["research", "codeintel"],
        "next_action_hint": "verify_contract_before_editing",
        "verified_claims": [
            {"claim": "demo.py prints a fixed banner", "evidence_refs": ["docs/demo.md"]}
        ],
        "retrieval_refs": ["docs/demo.md"],
        "blocked_assumptions": [],
        **extra,
    }


def test_research_auto_flow_clean_context_keeps_research_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caps = _run_auto_flow(tmp_path, monkeypatch, _flow_context())
    assert caps["research_used"] is True
    assert caps["research_gate_passed"] is True


@pytest.mark.parametrize(
    "extra",
    [
        {
            "verified_claims": [
                {"claim": "We recommend replacing the banner.", "evidence_refs": ["x"]}
            ]
        },
        {"doc_scout": {"hits": [{"snippet": "Patch plan: edit demo.py", "path": "docs/x.md"}]}},
        {"blocked_assumptions": ["The fix is to drop the banner."]},
    ],
    ids=["verified_claims", "doc_scout", "blocked_assumptions"],
)
def test_research_auto_flow_blocks_contaminated_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    caps = _run_auto_flow(tmp_path, monkeypatch, _flow_context(**extra))
    assert caps["research_used"] is True
    assert caps["research_gate_passed"] is False


# --- routes with no production caller (proof for #2216 review item 4) ---


def _python_sources() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    return [p for top in ("nexus", "scripts") for p in (root / top).rglob("*.py")]


def _importers(module: str) -> set[str]:
    import ast

    root = Path(__file__).resolve().parents[2]
    found: set[str] = set()
    package, _, leaf = module.rpartition(".")
    for path in _python_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
            if module in names or (package and f"{package}.{leaf}" in names):
                found.add(path.relative_to(root).as_posix())
    return found


def test_legacy_research_routes_have_no_live_importer() -> None:
    """The legacy facts_only/L0 research stage and the phase_factory research phase are
    reachable only through the archived legacy engine (ARCHIVED_2026-10-13-legacy-engine.md).
    A new importer outside that chain must wire P-CONTAM-01 first."""
    root = Path(__file__).resolve().parents[2]
    archived = "ARCHIVED 2026-10-13 legacy-engine"

    def is_archived(rel: str) -> bool:
        return archived in (root / rel).read_text(encoding="utf-8")

    assert _importers("nexus.engine.pipeline_stages") == {"nexus/engine/pipeline.py"}
    assert all(is_archived(rel) for rel in _importers("nexus.engine.pipeline_stages"))
    assert _importers("nexus.engine.phase_factory") <= {
        "nexus/engine/bootstrap.py",
        "nexus/engine/pipeline.py",
    }
    assert all(is_archived(rel) for rel in _importers("nexus.engine.phase_factory"))
    assert _importers("nexus.engine.phase_executors") <= {"nexus/engine/phase_factory.py"}
    # Direct handler users: the legacy phase executor, the uninstallable DI container,
    # and the port table that feeds the canonical executor (enforced).
    assert _importers("nexus.engine.phases.research") <= {
        "nexus/engine/phase_executors.py",
        "nexus/containers.py",
    }
    assert "dependency_injector" not in (root / "pyproject.toml").read_text(encoding="utf-8")
    port_users = {
        path.relative_to(root).as_posix()
        for path in _python_sources()
        if '"research.ResearchPhaseHandler"' in path.read_text(encoding="utf-8", errors="ignore")
    }
    assert port_users == {
        "nexus/core/capability_executor_registry.py",
        "nexus/engine/core_ports.py",
    }
