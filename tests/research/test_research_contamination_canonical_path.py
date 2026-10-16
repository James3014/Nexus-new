"""P-CONTAM-01 on the canonical research path (#2199).

Record-only (Owner option B, #2216): where the canonical research executor and the research
auto-flow accept research output, the contamination check RECORDS a contamination_signal
(detected / GUARD_ERROR) and never blocks; research status and research_gate_passed are
unchanged.  These tests go through the registered executor invoker and run_auto_flow, not
the guard alone.
"""

from __future__ import annotations

import dataclasses
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


def _signal(result: dict[str, Any]) -> dict[str, Any]:
    signal = _outcome(result)["contamination_signal"]
    assert signal["mode"] == "record_only" and signal["policy_id"] == "P-CONTAM-01"
    return signal


def _success(**extra: Any) -> dict[str, Any]:
    return {"source": "test", "status": "SUCCESS", "tokens_used": 1, **extra}


def test_canonical_research_flags_design_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total applies the discount; recommend a patch plan to fix it"]),
        task_id="contam-lang",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert _signal(result)["reason"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert _signal(result)["policy_id"] == "P-CONTAM-01"
    assert "design_plan" in _signal(result)["terms"]
    # record-only: the research output is still handed downstream
    assert outcome["result"]["findings"]


def test_canonical_research_flags_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], patch_plan="candidate_001"),
        task_id="contam-field",
    )
    assert _outcome(result)["semantic_status"] == "SUCCEEDED"
    assert result["gate_passed"] is True
    assert _signal(result)["reason"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert _signal(result)["terms"] == ["design_field"]


def test_canonical_research_flags_nested_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], raw={"winner": "candidate_b"}),
        task_id="contam-raw",
    )
    assert result["gate_passed"] is True
    assert _signal(result)["terms"] == ["design_field"]


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
    assert _signal(result)["detected"] is False


def test_canonical_research_guard_error_records_signal(
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
    assert result["gate_passed"] is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert _signal(result)["reason"] == "RESEARCH_CONTAMINATION_GUARD_ERROR"
    assert _signal(result)["detected"] is None


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
    task = "Find out why the rounding fix in compute_total changes the discounted total"

    def echoing(query: str) -> dict[str, Any]:
        return _success(
            findings=[f"Results for: {query}", "compute_total rounds after applying the discount."]
        )

    result = _run_research(tmp_path, monkeypatch, echoing, task_id="fp-echo", task=task)
    assert result["gate_passed"] is True


def test_canonical_research_echo_does_not_hide_other_contamination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = "Find out why the rounding fix in compute_total changes the discounted total"

    def echoing(query: str) -> dict[str, Any]:
        return _success(findings=[f"Results for: {query}", "We recommend replacing compute_total."])

    result = _run_research(tmp_path, monkeypatch, echoing, task_id="fp-echo-contam", task=task)
    assert result["gate_passed"] is True
    assert "we_recommend" in _signal(result)["terms"]


def test_canonical_research_flags_contaminated_blocked_assumptions(
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
    assert result["gate_passed"] is True
    assert _signal(result)["reason"] == "RESEARCH_CONTAMINATION_DETECTED"


def test_canonical_research_scans_findings_when_blocked_assumptions_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["Proposed patch: drop the rounding."], blocked_assumptions=["none"]),
        task_id="contam-ba-findings",
    )
    assert result["gate_passed"] is True
    assert _signal(result)["terms"] == ["label_prefix"]


@pytest.mark.parametrize(
    "extra",
    [
        {"summary": "Suggested fix: guard the division."},
        {"raw": {"answer": "I recommend changing compute_total."}},
        {"provider_notes": {"deep": ["Implementation plan: add a retry wrapper."]}},
    ],
    ids=["summary", "raw_answer", "non_schema_key"],
)
def test_canonical_research_flags_contaminated_non_findings_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], **extra),
        task_id="contam-field-" + next(iter(extra)),
    )
    assert result["gate_passed"] is True
    assert _signal(result)["reason"] == "RESEARCH_CONTAMINATION_DETECTED"


def test_guard_terms_parameter_keeps_legacy_default() -> None:
    from nexus.research.contamination_enforcement import CANONICAL_DESIGN_PATTERNS
    from nexus.research.contamination_guard import evaluate_research_contamination

    payload = {"constraints": ["a fix for the race landed in 2.3"]}
    assert evaluate_research_contamination(payload).detected_terms == ("fix",)
    assert (
        evaluate_research_contamination(payload, patterns=CANONICAL_DESIGN_PATTERNS).passed is True
    )
    cjk = {"constraints": ["根因在 parser；建議修改 parse() 的邊界判斷"]}
    assert evaluate_research_contamination(
        cjk, patterns=CANONICAL_DESIGN_PATTERNS
    ).detected_terms == ("zh_suggest",)


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
        # #2339 follow-up: the shared fixture's baseline patch comes from a fake model now.
        llm_mode=True,
        llm_baseline=True,
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
    assert caps["research_contamination_signal"]["detected"] is False


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
def test_research_auto_flow_flags_contaminated_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    import json

    caps = _run_auto_flow(tmp_path, monkeypatch, _flow_context(**extra))
    assert caps["research_used"] is True
    # record-only: the research gate is not flipped
    assert caps["research_gate_passed"] is True
    signal = caps["research_contamination_signal"]
    assert signal["detected"] is True and signal["mode"] == "record_only"
    assert signal["reason"] == "RESEARCH_CONTAMINATION_DETECTED"
    log = tmp_path / ".nexus" / "research" / "contamination_signals.jsonl"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["route"] == "research_flow_service.run_auto_flow"
    assert records[-1]["detected"] is True


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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))  # unparseable: fail
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


# --- #2216 round 2: natural phrasing, keys/objects, echoes, facts, quarantine, reachability ---


@pytest.mark.parametrize(
    "text",
    [
        "We should refactor compute_total to use a Decimal accumulator.",
        "The plan is to add a --strict flag to the parser.",
        "The solution is to add a lock around the counter.",
        "Proposed change: rename foo to bar.",
        "It is recommended to clamp the total before rounding.",
        "We propose adding a migration that backfills the column.",
        "Fix: guard the division by zero.",
        "This can be fixed by catching ValueError.",
        "To resolve this, update load() to handle empty files.",
        "--- a/pricing.py\n+++ b/pricing.py\n@@ -1 +1 @@\n-    return x*0.9\n+    return round(x*0.9,2)",
        "建議將 parse() 改為先檢查 None。",
        "解法是在 load() 加上 try/except。",
        "修正方式：在除法前檢查分母。",
        "我們應該重構 compute_total。",
        "需要修改 pricing.py 第 42 行。",
        "Ｗe recommend replacing the cache",
        "W\u200be recommend replacing the cache",
    ],
)
def test_canonical_check_detects_natural_design_phrasing(text: str) -> None:
    from nexus.research.contamination_enforcement import check_research_output

    verdict = check_research_output({"findings": [text]})
    assert verdict.passed is False
    assert verdict.reason == "RESEARCH_CONTAMINATION_DETECTED"


@pytest.mark.parametrize(
    "text",
    [
        "compute_total multiplies the subtotal by 0.9 when the discount flag is set.",
        "Release 2.3 includes a fix for the reconnect race; the patch changes the retry delay.",
        "The docs recommend 60 seconds; the recommended setting is jitter=full.",
        "解析器在遇到空字串時會丟出 ValueError，這個行為在 2.3 版仍然存在。",
    ],
)
def test_canonical_check_passes_factual_text(text: str) -> None:
    from nexus.research.contamination_enforcement import check_research_output

    assert check_research_output({"findings": [text]}).passed is True


@dataclasses.dataclass
class _Finding:
    text: str
    patch_plan: str = ""


class _Notes:
    def __init__(self) -> None:
        self.summary = "We recommend replacing the cache with an LRU."


class _Opaque:
    __slots__ = ("hidden",)

    def __init__(self) -> None:
        self.hidden = "We recommend replacing the cache."


@pytest.mark.parametrize(
    "output, reason",
    [
        (
            {"findings": ["ok"], "notes": {"We recommend replacing the cache with an LRU": 1}},
            "RESEARCH_CONTAMINATION_DETECTED",
        ),
        ({"findings": ["ok"], ("we recommend replacing x",): 1}, "RESEARCH_CONTAMINATION_DETECTED"),
        (
            {"findings": [_Finding(text="compute_total rounds half-up", patch_plan="x")]},
            "RESEARCH_CONTAMINATION_DETECTED",
        ),
        ({"findings": [_Notes()]}, "RESEARCH_CONTAMINATION_DETECTED"),
        ({"findings": [b"we recommend replacing the cache"]}, "RESEARCH_CONTAMINATION_DETECTED"),
        ({"findings": [_Opaque()]}, "RESEARCH_CONTAMINATION_GUARD_ERROR"),
    ],
    ids=["dict_key_text", "tuple_key", "dataclass_field", "object_attrs", "bytes", "opaque_object"],
)
def test_canonical_check_walks_keys_and_objects(output: Any, reason: str) -> None:
    from nexus.research.contamination_enforcement import check_research_output

    verdict = check_research_output(output)
    assert verdict.passed is False
    assert verdict.reason == reason


def test_canonical_check_walks_pydantic_models() -> None:
    pydantic = pytest.importorskip("pydantic")
    from nexus.research.contamination_enforcement import check_research_output

    class Pack(pydantic.BaseModel):
        findings: list[str]
        winner: str = ""

    verdict = check_research_output(Pack(findings=["ok"], winner="b"))
    assert verdict.passed is False
    assert verdict.detected_terms == ("design_field",)


def test_canonical_check_echo_rules() -> None:
    from nexus.research.contamination_enforcement import check_research_output

    clean_task = "Investigate why compute_total ignores the discount flag; report what we"
    # a design phrase that starts inside the echo and ends outside it still counts
    split = {"findings": [clean_task + " recommend: clamp first."]}
    assert check_research_output(split, echo_texts=(clean_task,)).passed is False
    # an echo that itself carries design language is never discounted
    design_task = "Research the parser. The fix is to accept trailing commas, confirm it."
    assert (
        check_research_output({"findings": [design_task]}, echo_texts=(design_task,)).passed
        is False
    )
    # a short echo is discounted only when clean: "fix:" is itself a design label
    assert (
        check_research_output({"findings": ["fix: results"]}, echo_texts=("fix:",)).passed is False
    )
    # a short clean task echoed verbatim passes
    assert (
        check_research_output(
            {"findings": ["Results for: rounding"]}, echo_texts=("rounding",)
        ).passed
        is True
    )


def test_research_facts_keep_findings_with_blocked_assumptions() -> None:
    from nexus.research.research_facts import build_research_facts

    facts = build_research_facts(
        research_pack={"findings": ["finding one"], "blocked_assumptions": ["assumption one"]},
        visibility_receipt={},
    )
    assert facts.constraints == ("assumption one", "finding one")


@pytest.mark.parametrize("broken", ["_research_part", "signal_from_verdict"])
def test_research_auto_flow_signal_error_records_guard_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    from nexus.research import contamination_enforcement

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("signal exploded")

    monkeypatch.setattr(contamination_enforcement, broken, boom)
    caps = _run_auto_flow(tmp_path, monkeypatch, _flow_context())
    assert caps["research_used"] is True
    assert caps["research_gate_passed"] is True
    signal = caps["research_contamination_signal"]
    assert signal["detected"] is None and signal["mode"] == "record_only"
    assert signal["reason"] == "RESEARCH_CONTAMINATION_GUARD_ERROR"


def test_research_auto_flow_does_not_quarantine_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.app import research_flow_service as rfs

    contaminated = {
        "schema": "nexus_research_context_v1",
        "role": "claim_scout",
        "hypothesis": "explain the websocket timeout race",
        "verified_claims": [
            {"claim": "We recommend replacing the banner.", "evidence_refs": ["x"]}
        ],
        "blocked_assumptions": ["api_contract_not_verified"],
    }
    seen: list[dict[str, Any]] = []
    real_compose = rfs.compose_capability_plan

    def capture(**kwargs: Any) -> Any:
        seen.append(kwargs["research_context"])
        return real_compose(**kwargs)

    monkeypatch.setattr(rfs, "_build_research_context", lambda **kwargs: dict(contaminated))
    monkeypatch.setattr(rfs, "compose_capability_plan", capture)
    rfs.build_route(
        repo_root=tmp_path,
        task_desc="explain the websocket timeout race",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
    )
    # record-only (option B): planning sees the research context unchanged
    assert seen[0] == contaminated


def test_canonical_research_contaminated_output_passes_with_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    findings = ["compute_total rounds half-up. We recommend replacing it with Decimal."]
    result = _run_research(tmp_path, monkeypatch, _success(findings=findings), task_id="sig-hit")
    outcome = _outcome(result)
    assert result["gate_passed"] is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert outcome["result"]["findings"] == findings
    signal = _signal(result)
    assert signal["detected"] is True
    assert signal["reason"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert "we_recommend" in signal["terms"]
    log = tmp_path / ".nexus" / "research" / "contamination_signals.jsonl"
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["route"] == "capability_executor_registry._exec_research"
    assert record["task_id"] == "sig-hit" and record["detected"] is True


def test_canonical_research_guard_error_passes_with_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research import contamination_guard

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("guard exploded")

    monkeypatch.setattr(contamination_guard, "evaluate_research_contamination", broken)
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total rounds half-up"]),
        task_id="sig-err",
    )
    assert result["gate_passed"] is True
    assert _outcome(result)["semantic_status"] == "SUCCEEDED"
    signal = _signal(result)
    assert signal["detected"] is None
    assert signal["reason"] == "RESEARCH_CONTAMINATION_GUARD_ERROR"


_LIVE_ENTRYPOINTS = (
    "scripts.engine.nexus_cli",
    "nexus.orchestrator.unified_mcp_gateway",
    "scripts.ops.nexus_mcp_server",
    "scripts.ops.nexus_mcp_gateway",
    "scripts.ops.nexus_mcp_gateway_http",
    "scripts.ops.mcp_gateway_durable",
)


def _static_import_closure(roots: tuple[str, ...]) -> set[str]:
    import ast

    repo = Path(__file__).resolve().parents[2]

    def module_file(module: str) -> Path | None:
        base = repo.joinpath(*module.split("."))
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None

    seen: set[str] = set()
    stack = list(roots)
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        path = module_file(module)
        if path is None:
            continue
        seen.add(module)
        parts = module.split(".")
        stack.extend(".".join(parts[:i]) for i in range(1, len(parts)))
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))  # unparseable: fail
        for node in ast.walk(tree):  # module-level and in-function imports
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base_parts = package.split(".")
                if node.level > 1:
                    base_parts = base_parts[: len(base_parts) - (node.level - 1)]
                base = (
                    node.module or ""
                    if not node.level
                    else ".".join(p for p in (*base_parts, node.module or "") if p)
                )
                names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            stack.extend(n for n in names if n.split(".")[0] in {"nexus", "scripts"})
    return seen


def test_legacy_research_routes_unreachable_from_live_entrypoints() -> None:
    reached = _static_import_closure(_LIVE_ENTRYPOINTS)
    # sanity: the closure does reach the two enforced research routes
    assert {"nexus.core.capability_executor_registry", "nexus.app.research_flow_service"} <= reached
    for legacy in (
        "nexus.engine.pipeline_stages",
        "nexus.engine.phase_factory",
        "nexus.engine.phase_executors",
    ):
        assert legacy not in reached, legacy
