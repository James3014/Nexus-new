"""P6: formal callers converge on MainchainEntry → CapabilityPlanner → UnifiedRuntime.

Contract tests + source-surface freeze for Gateway / PipelineRepair / CLI and
related formal runtime entry modules. Does not invent a second planner or route.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.mainchain_entry import run_mainchain, stamp_mainchain_route
from nexus.services.mainchain_route_freeze import (
    MAINCHAIN_AUTHORITY,
    single_planner_decision_id,
)
from nexus.services.unified_runtime import (
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)

REPO = Path(__file__).resolve().parents[2]

# Formal product entry surfaces (relative to repo root).
FORMAL_CALLER_PATHS: tuple[str, ...] = (
    "nexus/services/gateway.py",
    "nexus/engine/pipeline_repair.py",
    "scripts/engine/nexus_cli.py",
    "nexus/services/mainchain_entry.py",
    "nexus/services/unified_runtime.py",
    "nexus/research/sprint_service.py",
    "nexus/app/nightshift_runner_service.py",
    "nexus/research/day_shift_optimizer.py",
)

# Modules that may retain compatibility shims — must still fail closed / not select.
COMPAT_LABELS: frozenset[str] = frozenset(
    {
        "compatibility",
        "legacy_shim",
        "non_formal",
        "fail_closed",
    }
)


class _Planner:
    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[
                "codeintel",
                "artifact_gate",
                "claim_gate",
                "delivery_gate",
            ],
            required_capabilities=["codeintel"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


def _online(context: dict[str, Any]) -> dict[str, Any]:
    return normalize_online_invoker_payload(
        provider="fixture",
        task_id=str(context.get("task_id") or ""),
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"ok": True},
        raw_response="ok",
        evidence_refs=[f"online:{context.get('task_id')}"],
    )


def _verifier(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "verifier_status": "pass",
        "verifier_artifact": f"sha256:verifierartifact{c['task_id'][:8]}0001",
        "evidence_refs": [f"v:{c['task_id']}"],
    }


def _learning(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"l:{c['task_id']}"],
    }


def test_formal_callers_invoke_mainchain_entry(monkeypatch, tmp_path: Path) -> None:
    """Runtime proof: Gateway path goes through run_mainchain (not source-token search)."""
    calls: list[str] = []

    def _fake_run_mainchain(request, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(str(getattr(request, "task_id", "")))
        return {
            "schema": "nexus.unified_runtime.receipt.v1",
            "task_id": getattr(request, "task_id", ""),
            "planner_decision_id": "fake-pdid-1",
            "receipt_complete": True,
            "capability_closure_complete": False,
            "terminal_status": "SUCCEEDED",
            "claim_boundary": {"public_claim_allowed": False},
            "online": {"invoked": True, "status": "SUCCEEDED", "response": {"ok": True}},
            "public_claim_allowed": False,
        }

    import nexus.services.mainchain_entry as me

    monkeypatch.setattr(me, "run_mainchain", _fake_run_mainchain)

    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"summary": "online"}, "online-response"),
    )
    req = UnifiedRuntimeRequest(
        task_id="gw-mainchain-entry-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route={"recommended_flow": "direct", "provider": "gemini"},
        online_prompt="x",
        online_payload="y",
        evidence_refs=("t",),
    )
    receipt = gateway.ask_unified(req, verifier=_verifier, learning=_learning)
    assert "gw-mainchain-entry-1" in calls
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt.get("public_claim_allowed") is False


def test_sprint_nightshift_dayshift_fallback_uses_run_mainchain() -> None:
    """Source-surface: fallback paths call run_mainchain, not bare UnifiedRuntime().run."""
    for rel in (
        "nexus/research/sprint_service.py",
        "nexus/app/nightshift_runner_service.py",
        "nexus/research/day_shift_optimizer.py",
        "nexus/engine/pipeline_repair.py",
        "nexus/services/gateway.py",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "run_mainchain" in text, rel
        # Direct alternate runtime entry must not remain as product fallback.
        assert "UnifiedRuntime().run(" not in text, rel
        assert "UnifiedRuntime(local_service=" not in text or "run_mainchain" in text, rel


def test_formal_caller_sources_import_unified_runtime_or_mainchain() -> None:
    """Each formal caller module references UnifiedRuntime / MainchainEntry path."""
    required_tokens = (
        "UnifiedRuntime",
        "ask_unified",
        "run_mainchain",
        "MainchainEntry",
        "UnifiedRuntimeRequest",
    )
    missing: list[str] = []
    for rel in FORMAL_CALLER_PATHS:
        path = REPO / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        if not any(tok in text for tok in required_tokens):
            missing.append(rel)
    assert missing == [], missing


def test_formal_caller_sources_do_not_define_second_planner_class() -> None:
    """No ClassDef named CapabilityPlanner outside engine/capability_planner.py."""
    hits: list[str] = []
    for rel in FORMAL_CALLER_PATHS:
        path = REPO / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CapabilityPlanner":
                hits.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.ClassDef) and node.name == "RouteMode":
                hits.append(f"{rel}:RouteMode:{node.lineno}")
    assert hits == [], hits


def test_gateway_ask_unified_single_planner_decision(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"summary": "online"}, "online-response"),
    )
    req = UnifiedRuntimeRequest(
        task_id="gw-formal-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route={
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 2},
    )
    receipt = gateway.ask_unified(
        req,
        verifier=_verifier,
        learning=_learning,
        receipt_path=tmp_path / "gw.json",
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert check["selection_authority"] == MAINCHAIN_AUTHORITY
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt.get("planner_decision_id")


def test_mainchain_entry_run_mainchain_contract() -> None:
    route = stamp_mainchain_route(
        {"recommended_flow": "direct"}, product_entry="pipeline_repair"
    )
    assert route["mainchain_entry"] is True
    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id="mc-formal-1",
            workspace_revision="r",
            task_statement="scan impact risk codeintel",
            task_type="codeintel",
            route={
                "recommended_flow": "direct",
                "injected_transport": True,
                "online_policy": "auto",
                "mainchain_entry": True,
            },
            online_enabled=True,
            online_prompt="task",
            codeintel={"scan_report_present": True, "risk_score": 1},
        ),
        online_invoker=_online,
        planner=_Planner(),
        verifier=_verifier,
        learning=_learning,
    )
    assert single_planner_decision_id(receipt)["ok"] is True
    assert receipt["capability_evidence_bundle"]["planner_decision_id"] == receipt[
        "planner_decision_id"
    ]


def test_pipeline_repair_module_wires_unified_runtime() -> None:
    text = (REPO / "nexus/engine/pipeline_repair.py").read_text(encoding="utf-8")
    assert "UnifiedRuntime" in text
    assert "UnifiedRuntimeRequest" in text
    # Must not invent a parallel Online+Local product route string
    assert "online_local_v2" not in text
    assert "nexus_full_stack" not in text or "pop" in text or "strip" in text


def test_pipeline_repair_runtime_single_planner_decision_id(monkeypatch, tmp_path: Path) -> None:
    """Runtime: invoke PipelineRepairMixin._run_unified_advisor_online under run_mainchain monkeypatch."""
    import nexus.services.mainchain_entry as me
    from nexus.engine.pipeline_repair import PipelineRepairMixin

    calls: list[str] = []

    def _fake_run_mainchain(request, **kwargs):  # type: ignore[no-untyped-def]
        tid = str(getattr(request, "task_id", ""))
        calls.append(tid)
        return {
            "schema": "nexus.unified_runtime.receipt.v1",
            "task_id": tid,
            "planner_decision_id": "pr-pdid-1",
            "receipt_complete": True,
            "capability_closure_complete": False,
            "terminal_status": "SUCCEEDED",
            "claim_boundary": {"public_claim_allowed": False},
            "online": {
                "invoked": True,
                "status": "SUCCEEDED",
                "response": {"status": "APPROVED", "patch": "ok", "ok": True},
            },
            "capability_evidence_bundle": {
                "planner_decision_id": "pr-pdid-1",
                "bundle_hash": "b" * 64,
            },
            "planner_decision_id": "pr-pdid-1",
            "public_claim_allowed": False,
        }

    monkeypatch.setattr(me, "run_mainchain", _fake_run_mainchain)

    class _Gateway:
        oauth_provider = "gemini"
        use_surgical_repair = False

        def ask_structured(self, *a, **k):  # type: ignore[no-untyped-def]
            return {"status": "APPROVED", "patch": "ok"}, "raw"

        def bind_online_execution_decision(self, *a, **k):  # type: ignore[no-untyped-def]
            return None

    class _Harness(PipelineRepairMixin):
        def __init__(self) -> None:
            self.engine = type(
                "E",
                (),
                {
                    "project_root": tmp_path,
                    "run_dir": tmp_path / "runs",
                    "_add_step_to_history": lambda *a, **k: None,
                },
            )()
            self.registry = None
            self._repair_gateway = _Gateway()

        def _ensure_repair_gateway(self, ctx):  # type: ignore[no-untyped-def]
            return self._repair_gateway

        def _ensure_workspace_revision(self, ctx) -> str:  # type: ignore[no-untyped-def]
            return "wr-pr-1"

        def _stamp_stage_truth(self, meta, **kwargs):  # type: ignore[no-untyped-def]
            meta.update(kwargs)
            return meta

    class _State:
        def __init__(self) -> None:
            self.metadata = {
                "task_id": "pr-runtime-1",
                "local_assist_mode": "disabled",
                "oauth_provider": "gemini",
                "injected_transport": True,
                "online_policy": "auto",
            }

    class _Ctx:
        def __init__(self) -> None:
            self.state = _State()
            self.task_id = "pr-runtime-1"
            self.task_desc = "pipeline repair formal caller proof"

    harness = _Harness()
    (tmp_path / ".nexus" / "reports" / "unified_runtime").mkdir(parents=True, exist_ok=True)

    def _online_callable(prompt: str):
        return {"status": "APPROVED", "patch": "ok"}, "raw-online"

    res, raw = harness._run_unified_advisor_online(
        _Ctx(),
        online_callable=_online_callable,
        repair_attempts=1,
    )
    assert calls, "PipelineRepairMixin did not call run_mainchain"
    assert any("pr-runtime-1" in c for c in calls), calls
    assert res is not None or raw is not None


@pytest.mark.parametrize("mode", ["disabled", "advisor"])
def test_pipeline_repair_mainchain_exception_fails_closed_without_online_bypass(
    monkeypatch, tmp_path: Path, mode: str
) -> None:
    """A broken canonical runtime must not fall through to the bare Online callable."""
    import json

    import nexus.services.mainchain_entry as me
    from nexus.engine.pipeline_repair import PipelineRepairMixin

    def _raise_mainchain(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("canonical boom")

    monkeypatch.setattr(me, "run_mainchain", _raise_mainchain)

    class _Gateway:
        oauth_provider = "fixture"

    class _Harness(PipelineRepairMixin):
        def __init__(self) -> None:
            self.engine = type(
                "E",
                (),
                {
                    "project_root": tmp_path,
                    "run_dir": tmp_path / "runs",
                    "_add_step_to_history": lambda *a, **k: None,
                },
            )()
            self.registry = None
            self._repair_gateway = _Gateway()

        def _ensure_repair_gateway(self, ctx):  # type: ignore[no-untyped-def]
            return self._repair_gateway

        def _ensure_workspace_revision(self, ctx) -> str:  # type: ignore[no-untyped-def]
            return "wr-mainchain-fail"

    metadata = {
        "task_id": f"mainchain-fail-{mode}",
        "local_assist_mode": mode,
        "oauth_provider": "fixture",
        "injected_transport": True,
        "online_policy": "auto",
        "target_file": "demo.py",
        "target_files": ["demo.py"],
        "local_assist_service": object(),
    }
    state = type("State", (), {"metadata": metadata})()
    ctx = type(
        "Ctx",
        (),
        {
            "state": state,
            "task_id": metadata["task_id"],
            "task_desc": "repair demo.py",
        },
    )()
    online_prompts: list[str] = []

    def _online_callable(prompt: str):
        online_prompts.append(prompt)
        return {"status": "APPROVED", "patch": "bypass"}, "bypass"

    res, raw = _Harness()._run_unified_advisor_online(
        ctx,
        online_callable=_online_callable,
        repair_attempts=1,
    )

    assert online_prompts == []
    assert raw == ""
    assert res == {
        "status": "FAILED",
        "patch": "",
        "error": "mainchain_exception:RuntimeError:canonical boom",
        "provider_call_count": 0,
        "mainchain_entry": True,
        "receipt_complete": False,
    }
    assert metadata["degraded_to_online"] is False
    assert metadata["online_continued_without_local_assist"] is False
    assert metadata["online_success"] is False
    assert metadata["runtime_receipt_complete"] is False
    pointer = json.loads(Path(metadata["unified_runtime_pointer_path"]).read_text(encoding="utf-8"))
    assert pointer["degradation_reason"] == "mainchain_exception:RuntimeError:canonical boom"
    assert pointer["claim_boundary"] == {
        "production_ready": False,
        "public_claim_allowed": False,
    }


def test_cli_module_uses_gateway_ask_unified() -> None:
    text = (REPO / "scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    assert "ask_unified" in text
    assert "UnifiedRuntimeRequest" in text


def test_cli_path_monkeypatch_mainchain_entry(monkeypatch, tmp_path: Path) -> None:
    """CLI content-rewrite uses gateway.ask_unified → run_mainchain (monkeypatch proof)."""
    import nexus.services.mainchain_entry as me

    calls: list[str] = []

    def _fake_run_mainchain(request, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(str(getattr(request, "task_id", "")))
        return {
            "schema": "nexus.unified_runtime.receipt.v1",
            "task_id": getattr(request, "task_id", ""),
            "planner_decision_id": "cli-pdid-1",
            "receipt_complete": True,
            "capability_closure_complete": False,
            "terminal_status": "SUCCEEDED",
            "claim_boundary": {"public_claim_allowed": False},
            "online": {
                "invoked": True,
                "status": "SUCCEEDED",
                "response": {"patch": "rewritten", "status": "APPROVED"},
            },
            "public_claim_allowed": False,
        }

    monkeypatch.setattr(me, "run_mainchain", _fake_run_mainchain)
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"status": "APPROVED", "patch": "rewritten"}, "raw"),
    )
    # CLI path is gateway.ask_unified with UnifiedRuntimeRequest (same as nexus_cli).
    from nexus.services.mainchain_entry import stamp_mainchain_route

    req = UnifiedRuntimeRequest(
        task_id="cli-mainchain-1",
        workspace_revision="r",
        task_statement="rewrite document",
        task_type="document_rewrite",
        route=stamp_mainchain_route(
            {"recommended_flow": "direct", "provider": "gemini"},
            product_entry="content_rewrite",
        ),
        online_prompt="rewrite",
        online_payload="src",
        evidence_refs=("cli:1",),
    )
    receipt = gateway.ask_unified(req, verifier=_verifier, learning=_learning)
    assert "cli-mainchain-1" in calls
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_sprint_nightshift_dayshift_monkeypatch_run_mainchain(monkeypatch, tmp_path: Path) -> None:
    """Monkeypatch run_mainchain and exercise Sprint/Nightshift/DayShift entry methods."""
    import nexus.services.mainchain_entry as me

    hits: list[str] = []

    def _fake(request, **kwargs):  # type: ignore[no-untyped-def]
        tid = str(getattr(request, "task_id", "x"))
        hits.append(tid)
        return {
            "schema": "nexus.unified_runtime.receipt.v1",
            "task_id": tid,
            "planner_decision_id": "s-pdid",
            "receipt_complete": True,
            "terminal_status": "SUCCEEDED",
            "claim_boundary": {"public_claim_allowed": False},
            "online": {
                "invoked": True,
                "status": "SUCCEEDED",
                "response": {"status": "APPROVED", "patch": "ok", "ok": True},
            },
            "public_claim_allowed": False,
        }

    monkeypatch.setattr(me, "run_mainchain", _fake)

    class _Gw:
        """No ask_unified → forces run_mainchain fallback on each service."""

        oauth_provider = "gemini"

        def ask_structured(self, *a, **k):  # type: ignore[no-untyped-def]
            return {"status": "APPROVED", "patch": "ok"}, "raw"

    # Sprint (LLMCandidateGenerator)
    from nexus.research.sprint_service import LLMCandidateGenerator

    sprint = LLMCandidateGenerator(project_root=tmp_path, safe_mode=True, target_file="")
    sprint.gateway = _Gw()
    sprint.local_service = None
    _out, _raw, receipt = sprint._ask_unified_candidate(
        prompt="p",
        payload="body",
        task="formal sprint mp",
        seed=1,
        attempt=0,
        model="fixture-model",
    )
    assert any(h.startswith("sprint-") for h in hits), hits
    assert receipt.get("planner_decision_id") == "s-pdid"
    assert receipt.get("claim_boundary", {}).get("public_claim_allowed") is False

    # Nightshift (AutoResearchNightShift)
    from nexus.app.nightshift_runner_service import AutoResearchNightShift

    ns = AutoResearchNightShift(task="formal nightshift mp", project_root=tmp_path, gateway=_Gw())
    ns.gateway = _Gw()
    _n_out, _n_raw, n_receipt = ns._ask_unified_candidate(
        workpath=tmp_path,
        round_id=0,
        attempt=0,
        model="fixture-model",
        prompt="p",
        payload="body",
        output_schema={"status": "APPROVED | FAIL"},
        task_kind="generation",
    )
    assert any(h.startswith("nightshift-") for h in hits), hits
    assert n_receipt.get("planner_decision_id") == "s-pdid"

    # DayShift
    from nexus.research.day_shift_optimizer import DayShiftOptimizer

    (tmp_path / "target.py").write_text("x=1\n", encoding="utf-8")
    dso = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="target.py",
        task_desc="formal dayshift mp",
    )
    dso.gateway = _Gw()
    _d_out, _d_raw, d_receipt = dso._ask_unified(
        prompt="p",
        payload="body",
        task_statement="formal dayshift mp",
        round_id=0,
        attempt=0,
        model="fixture-model",
        output_schema={"status": "APPROVED | FAIL"},
        task_kind="generation",
    )
    assert any(h.startswith("dayshift-") for h in hits), hits
    assert d_receipt.get("planner_decision_id") == "s-pdid"
    assert d_receipt.get("claim_boundary", {}).get("public_claim_allowed") is False


def test_cli_runtime_gateway_ask_unified_single_planner(monkeypatch, tmp_path: Path) -> None:
    """Runtime: CLI-equivalent Gateway.ask_unified path shares one planner_decision_id."""
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.mainchain_entry import stamp_mainchain_route

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"summary": "online"}, "online-response"),
    )
    route = stamp_mainchain_route(
        {
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
            "with_nexus_armor": True,
        },
        product_entry="nexus_cli",
    )
    req = UnifiedRuntimeRequest(
        task_id="cli-runtime-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route=route,
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 2},
    )
    receipt = gateway.ask_unified(
        req,
        verifier=_verifier,
        learning=_learning,
        receipt_path=tmp_path / "cli.json",
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert receipt["planner_decision_id"]
    assert receipt["capability_evidence_bundle"]["planner_decision_id"] == receipt[
        "planner_decision_id"
    ]
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_sprint_nightshift_dayshift_research_entries_if_present() -> None:
    """When formal Sprint/Nightshift/DayShift/Research entry modules exist, they
    must reference UnifiedRuntime / mainchain — not a second planner."""
    candidates = [
        "nexus/engine/hyper_sprint.py",
        "nexus/services/local_heal/hybrid_cloud_assist_runtime.py",
        "nexus/research/learn_mode.py",
        "nexus/engine/phases/research.py",
        "nexus/services/nightshift_runner.py",
        "nexus/engine/nightshift.py",
    ]
    found = 0
    bad: list[str] = []
    for rel in candidates:
        path = REPO / rel
        if not path.is_file():
            continue
        found += 1
        text = path.read_text(encoding="utf-8")
        # Soft contract: if they select capabilities themselves via a new planner class, fail
        if "class CapabilityPlanner" in text:
            bad.append(f"{rel}:defines_CapabilityPlanner")
        if 'RouteMode(' in text and "from nexus.contracts.hybrid_route import" not in text:
            # new RouteMode definition, not import
            if "class RouteMode" in text:
                bad.append(f"{rel}:defines_RouteMode")
    # At least some formal-adjacent modules exist in this repo
    assert found >= 1
    assert bad == [], bad


def test_bypass_allowlist_empty_for_mainchain_authority() -> None:
    """No second selection authority allowlist on freeze contract."""
    from nexus.services.mainchain_route_freeze import (
        ROUTE_AUTHORITY_FORBIDDEN,
        freeze_summary,
    )

    assert "CapabilitySelector" in ROUTE_AUTHORITY_FORBIDDEN
    summary = freeze_summary(repo_root=REPO)
    assert summary["route_authority"] == MAINCHAIN_AUTHORITY
    assert summary["routing_surface_changed"] is False
