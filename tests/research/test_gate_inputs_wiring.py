"""Wiring PR-4: the sprint feeds the preflight gates their inputs, so the capabilities the
#2212 audit classified ``blocked_missing_inputs`` evaluate (SUCCEEDED or evaluated-rejected),
and the strict-lane with-Nexus prompt text does not change."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from nexus.research.gate_inputs import FED_CAPABILITIES, sprint_gate_inputs

TASK = (
    "Repair a flaky-looking timeout calculation without deleting assertions; success requires "
    "preserving the behavioral contract and validating the actual failing branch."
)
ORIGINAL = (
    "def remaining_ms(start_ms, now_ms, timeout_ms):\n    return timeout_ms - now_ms - start_ms\n"
)
VISIBLE = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
    "from target import remaining_ms\n\n\ndef test_remaining_ms_simple_elapsed_case():\n"
    "    assert remaining_ms(100, 125, 50) == 25\n"
)
HIDDEN = "from pathlib import Path\nPath(__file__).with_name('HIDDEN_RAN').write_text('x')\n"


def _detect_receipt_only() -> bool:
    """``runtime_supports_receipt_only()`` re-evaluated (it is ``lru_cache``d)."""

    from nexus.research.gate_inputs import runtime_supports_receipt_only

    runtime_supports_receipt_only.cache_clear()
    return runtime_supports_receipt_only()


@pytest.fixture(autouse=True)
def _fresh_receipt_only_detection() -> Any:
    """No test sees a detection result cached under another test's runtime patches."""

    from nexus.research.gate_inputs import runtime_supports_receipt_only

    runtime_supports_receipt_only.cache_clear()
    yield
    runtime_supports_receipt_only.cache_clear()


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "target.py").write_text(ORIGINAL, encoding="utf-8")
    (root / "test_visible.py").write_text(VISIBLE, encoding="utf-8")
    (root / "test_hidden.py").write_text(HIDDEN, encoding="utf-8")
    return root


def _run(
    root: Path,
    tmp_path: Path,
    *,
    feed: bool,
    task: str = TASK,
    source: str = ORIGINAL,
    prompt: str = "",
    extra_route: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    from nexus.services.mainchain_entry import run_mainchain
    from nexus.services.unified_runtime import UnifiedRuntimeRequest, build_online_route

    task_id = "sprint-gateinputs-s0-a1"
    route = build_online_route(
        recommended_flow="direct", gateway_provider="agy", local_enabled=False
    )
    route["with_nexus_armor"] = True
    route["route_features"] = {"risk_score": 55}
    route.update(extra_route or {})
    codeintel: dict[str, Any] = {}
    if feed:
        inputs = sprint_gate_inputs(
            repo_root=root,
            task=task,
            target_file="target.py",
            test_file="test_visible.py",
            source_code=source,
            route=route,
        )
        codeintel = inputs["codeintel"]
        route["workspace_root"] = inputs["workspace_root"]
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="fixture-rev",
        task_statement=task,
        task_type="repair",
        route=route,
        codeintel=codeintel,
        online_prompt=prompt or "Task: " + task,
        online_payload="x",
        online_phase="R",
        online_model_name="gemini-3.8-flash-medium",
        online_output_schema={"status": "APPROVED | FAIL"},
    )
    prompts: list[str] = []

    def online(context: Any) -> dict[str, Any]:
        prompts.append(str(context.get("online_prompt") or ""))
        return {
            "task_id": task_id,
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "response": {"status": "APPROVED", "patch": source},
            "evidence_refs": [f"online:{task_id}"],
        }

    online.provider = "agy"  # type: ignore[attr-defined]
    online.online_invoker_provider = "agy"  # type: ignore[attr-defined]

    def verifier(_context: Any) -> dict[str, Any]:
        return {"task_id": task_id, "status": "pass", "evidence_refs": [f"verifier:{task_id}"]}

    cwd = os.getcwd()
    os.chdir(root)
    try:
        receipt = run_mainchain(
            request,
            online_invoker=online,
            verifier=verifier,
            receipt_path=tmp_path / f"unified_{root.name}_{int(feed)}.json",
            with_nexus_armor=True,
        )
    finally:
        os.chdir(cwd)
    return dict(receipt), prompts


def _sprint_run(
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    feed: bool,
    model_context: bool = False,
) -> tuple[Any, dict[str, Any], list[str]]:
    """Like ``_run``, but the request (route included) is assembled by the sprint itself
    (``LLMCandidateGenerator._ask_unified_candidate``), so the strict lane's
    ``receipt_only_capabilities`` declaration comes from production code, never from the
    test.  ``model_context`` wraps the online invoker with the runtime's
    ``wrap_online_invoker`` so the prompt carries ``[NEXUS MODEL CONTEXT]``.  Returns
    ``(request, receipt, prompts)``."""

    from nexus.research.sprint_service import LLMCandidateGenerator
    from nexus.services.mainchain_entry import run_mainchain

    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", "1" if feed else "0")
    generator = LLMCandidateGenerator(
        root,
        safe_mode=True,
        target_file="target.py",
        route_signals={"route_features": {"risk_score": 55}},
    )
    generator._workspace_revision = lambda: "fixture-rev"  # type: ignore[method-assign]
    generator.gate_input_test_file = "test_visible.py"
    captured: dict[str, Any] = {"prompts": []}

    def online(context: Any) -> dict[str, Any]:
        captured["prompts"].append(str(context.get("online_prompt") or ""))
        task_id = str(context.get("task_id") or captured["request"].task_id)
        return {
            "task_id": task_id,
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "response": {"status": "APPROVED", "patch": ORIGINAL},
            "evidence_refs": [f"online:{task_id}"],
        }

    online.provider = "agy"  # type: ignore[attr-defined]
    online.online_invoker_provider = "agy"  # type: ignore[attr-defined]

    def ask_unified(request: Any, **kwargs: Any) -> dict[str, Any]:
        captured["request"] = request
        invoker: Any = online
        if model_context:
            from nexus_runtime.task_context import wrap_online_invoker

            invoker = wrap_online_invoker(online)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            return dict(
                run_mainchain(
                    request,
                    online_invoker=invoker,
                    verifier=kwargs["verifier"],
                    receipt_path=tmp_path / f"sprint_{int(feed)}.json",
                    with_nexus_armor=True,
                )
            )
        finally:
            os.chdir(cwd)

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    _out, _raw, receipt = generator._ask_unified_candidate(
        prompt="Task: " + TASK,
        payload="x",
        task=TASK,
        seed=0,
        attempt=1,
        model="gemini-3.8-flash-medium",
        source_code=ORIGINAL,
    )
    return captured["request"], receipt, captured["prompts"]


# Missing-input refusal code of every fed capability before wiring PR-4.
BLOCKED_BEFORE = {
    "pregate": "EXPLICIT_VERIFY_COMMANDS_REQUIRED",
    "harness_preflight_sensor": "VERIFY_COMMAND_WIRING_REQUIRED",
    "plan_quality_gate": "PLAN_QUALITY_CONTEXT_REQUIRED",
    "mempalace_gate": "MEMPALACE_ARTIFACT_CONTEXT_REQUIRED",
    "memory": "PROJECT_MEMORY_CONTEXT_REQUIRED",
    "codeintel": "TARGET_SYMBOL_REQUIRED",
}
_HEX = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
_EV_ID = re.compile(r"(ev_cap_[a-z_]+?)_[0-9a-f]{8}\b")


def _outcome(record: dict[str, Any]) -> dict[str, Any]:
    raw_response = record.get("response")
    response: dict[str, Any] = raw_response if isinstance(raw_response, dict) else {}
    raw_inner = response.get("response")
    inner: dict[str, Any] = raw_inner if isinstance(raw_inner, dict) else {}
    raw_outcome = inner.get("outcome")
    return raw_outcome if isinstance(raw_outcome, dict) else inner


def _attestations(receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from nexus.research.flow.unified_capability_projection import (
        overlay_unified_capability_receipts,
        project_unified_capability_stages,
    )

    stages = project_unified_capability_stages([receipt])
    flow = [{"name": s["name"], "selected": True, "invoked": False} for s in stages]
    return {r["name"]: r for r in overlay_unified_capability_receipts(flow, stages)}


def _mask_run_identity(prompt: str) -> str:
    """Per-run random evidence ids and content hashes (they already differ run to run)."""

    return _HEX.sub("<sha256>", _EV_ID.sub(r"\1_<rand>", prompt))


def _install_target_python(root: Path) -> None:
    """pregate runs ``python3`` from ``<root>/.venv/bin`` (cli_pregate); point it at pytest."""

    import sys

    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    shim = venv_bin / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)


def test_gate_inputs_come_from_the_task_contract_and_never_name_a_hidden_test(
    tmp_path: Path,
) -> None:
    from nexus.research.sprint_service import _canonical_fact_key_allowed

    root = _workspace(tmp_path)
    route = {"route_features": {"risk_score": 55}}
    codeintel = sprint_gate_inputs(
        repo_root=root,
        task=TASK,
        target_file="target.py",
        test_file="test_visible.py",
        source_code=ORIGINAL,
        route=route,
    )["codeintel"]
    assert codeintel["verify_commands"] and "test_visible.py" in codeintel["verify_commands"][0]
    assert codeintel["verify_commands"][0].split()[-2:] == ["--", "test_visible.py"]
    assert codeintel["target_symbol"] == "remaining_ms"
    assert codeintel["target_files"] == ["target.py"] and codeintel["intent_pass"] is True
    assert codeintel["handoff_readiness"] == 1.0
    # Never in codeintel: fields the CodeIntel prompt summary renders.
    for key in ("risk_score", "scan_report_present", "impact_report_present", "risk_reason"):
        assert key not in codeintel
    assert "test_hidden" not in json.dumps(codeintel)
    provenance = codeintel["gate_input_provenance"]
    assert set(codeintel) - {"gate_input_provenance"} <= set(provenance)
    assert provenance["risk_score"] == "flow_route.route_features.risk_score"

    def keys(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [k for k, v in value.items() for k in [k, *keys(v)]]
        if isinstance(value, list):
            return [k for item in value for k in keys(item)]
        return []

    # The canonical seam rejects the whole request on route/model/... keys (file names too).
    assert all(_canonical_fact_key_allowed(key) for key in keys(codeintel))

    hidden = sprint_gate_inputs(
        repo_root=root, task=TASK, target_file="target.py", test_file="test_hidden.py"
    )["codeintel"]
    for key in ("verify_commands", "acceptance_criteria", "impact_map", "target_symbol"):
        assert key not in hidden, key
    assert hidden["handoff_readiness"] < 1.0
    assert "test_hidden" not in json.dumps(hidden)


def test_fed_gates_evaluate_instead_of_refusing_for_missing_inputs(
    governed_admission: None, tmp_path: Path
) -> None:
    root = _workspace(tmp_path)
    _install_target_python(root)
    before, _ = _run(root, tmp_path, feed=False)
    after, _ = _run(root, tmp_path, feed=True)
    before_att = _attestations(before)
    after_att = _attestations(after)

    for name, code in BLOCKED_BEFORE.items():
        record = before["capability_results"][name]
        assert _outcome(record).get("semantic_status") == "BLOCKED", name
        assert _outcome(record).get("error") == code, name
        assert before_att[name]["attestation"] == "blocked_missing_inputs", name
        assert before_att[name]["blocked_reason"] == code, name

        record = after["capability_results"][name]
        outcome = _outcome(record)
        assert outcome.get("semantic_status") in {"SUCCEEDED", "FAILED"}, (name, outcome)
        assert outcome.get("error") in (None, ""), (name, outcome)
        assert record["response"]["input_provenance"], name
        attestation = after_att[name]["attestation"]
        assert attestation in {"real", "failed_or_refused", "real_self_reported"}, name
        if outcome["semantic_status"] == "FAILED":
            # Evaluated and rejected: never a real success.
            assert record["gate_passed"] is False and attestation != "real", name

    # pregate ran exactly the visible test on the unmodified source (it fails there).
    pregate = _outcome(after["capability_results"]["pregate"])
    assert pregate["semantic_status"] == "FAILED" and pregate["command_count"] == 1
    result = pregate["results"][0]
    assert result["cmd"].endswith("-- test_visible.py") and "1 failed" in result["stdout_tail"]
    assert not (root / "HIDDEN_RAN").exists()
    provenance = after["capability_results"]["pregate"]["response"]["input_provenance"]
    assert provenance["verify_commands"] == "gate_inputs.pregate_verify_argv(config.test_file)"
    assert after["capability_results"]["plan_quality_gate"]["status"] == "SUCCEEDED"
    plan = after["capability_results"]["plan_quality_gate"]["response"]["input_provenance"]
    assert plan["risk_score"] == "flow_route.route_features.risk_score"


def test_strict_lane_prompt_text_is_identical_with_and_without_gate_inputs(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.gate_inputs import fed_capability_names
    from scripts.bench import prompt_symmetry_audit as psa

    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    root = _workspace(tmp_path)
    _install_target_python(root)
    # Requests assembled by the sprint: the strict lane declares the receipt-only key itself.
    before_request, _before, before_prompts = _sprint_run(root, tmp_path, monkeypatch, feed=False)
    after_request, after, after_prompts = _sprint_run(root, tmp_path, monkeypatch, feed=True)
    for request in (before_request, after_request):
        assert request.route["receipt_only_capabilities"] == sorted(fed_capability_names())
    assert dict(before_request.codeintel) == {} and after_request.codeintel["verify_commands"]
    assert after["capability_results"]["plan_quality_gate"]["status"] == "SUCCEEDED"
    assert len(before_prompts) == len(after_prompts) == 1
    raw_before, raw_after = before_prompts[0], after_prompts[0]
    # Byte-identical once the per-run random ids and content hashes are masked; nothing else
    # (no status, no payload, no line) differs.
    assert _mask_run_identity(raw_after) == _mask_run_identity(raw_before)
    assert len(raw_after.splitlines()) == len(raw_before.splitlines())
    # Same prompt-symmetry verdicts as before (the bench audit's extra-line classifier).
    material = psa.TaskMaterial(
        task_id="gate-inputs",
        visible_test=VISIBLE,
        hidden_test=HIDDEN,
        source=ORIGINAL,
        task_desc=TASK,
    )
    reference = "Task: " + TASK
    checks = [
        {
            k: [_mask_run_identity(x) for x in v]
            for k, v in psa.classify_extra_lines(prompt, reference, material).items()
        }
        for prompt in (raw_before, raw_after)
    ]
    assert checks[0] == checks[1]


def test_treatment_lane_prompt_shows_the_evaluated_verdicts(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    root = _workspace(tmp_path)
    _, before_prompts = _run(root, tmp_path, feed=False)
    _, after_prompts = _run(root, tmp_path, feed=True)

    def block(prompt: str, header: str) -> str:
        lines = prompt.splitlines()
        return lines[lines.index(header) + 1]

    evidence = json.loads(block(after_prompts[0], "[NEXUS CAPABILITY EVIDENCE]"))
    status = {e.get("name"): e["status"] for e in evidence["entries"]}
    assert status["plan_quality_gate"] == "REAL_INVOKED"
    # The CodeIntel summary is not fed by the gate inputs.
    summary = "[NEXUS CODEINTEL SUMMARY]"
    assert block(after_prompts[0], summary) == block(before_prompts[0], summary)


def test_withheld_view_keeps_other_entries_and_skips() -> None:
    from nexus.services.online_nexus_context import withhold_fed_gate_verdicts

    bundle = {
        "entries": [
            {"name": "learn_mode", "status": "REAL_INVOKED", "success": True},
            {
                "name": "memory",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "consumer_payload": {"fields": {"hit_count": 3}},
                "has_consumer_payload": True,
            },
            {"name": "pregate", "status": "SKIPPED", "skipped": True},
            {"name": "plan_quality_gate", "status": "EVALUATED_REJECTED", "success": False},
            {"name": "research", "status": "EVALUATED_REJECTED", "success": False},
        ]
    }
    out = withhold_fed_gate_verdicts(bundle)
    assert out["entries"][0] == bundle["entries"][0]
    assert out["entries"][1]["status"] == "INVOKED_NOT_SUCCESS"
    assert out["entries"][1]["consumer_payload"] == {} and out["entries"][1]["success"] is False
    # A fed capability is one opaque placeholder whatever its status (here SKIPPED).
    assert out["entries"][2]["evidence_ids"] == [] and out["entries"][2]["skipped"] is False
    # The runtime patch's EVALUATED_REJECTED renders as the pre-patch status in the prompt.
    assert [e["status"] for e in out["entries"][3:]] == ["INVOKED_NOT_SUCCESS"] * 2
    assert bundle["entries"][1]["status"] == "REAL_INVOKED"  # the sealed bundle is untouched
    assert FED_CAPABILITIES == frozenset(BLOCKED_BEFORE)


def _capture_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from nexus.research.sprint_service import LLMCandidateGenerator

    root = _workspace(tmp_path)
    generator = LLMCandidateGenerator(root, safe_mode=True, target_file="target.py")
    generator._workspace_revision = lambda: "revision-gate-inputs"  # type: ignore[method-assign]
    generator.gate_input_test_file = "test_visible.py"
    captured: dict[str, Any] = {}

    def ask_unified(request: Any, **_kwargs: Any) -> dict[str, Any]:
        captured["request"] = request
        return {"task_id": request.task_id}

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    generator._ask_unified_candidate(
        prompt="p", payload="x", task=TASK, seed=0, attempt=1, model="m", source_code=ORIGINAL
    )
    return captured["request"], root


def test_sprint_request_carries_gate_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_SPRINT_GATE_INPUTS", raising=False)
    request, root = _capture_request(tmp_path, monkeypatch)
    assert request.codeintel["verify_commands"][0].endswith("-- test_visible.py")
    assert request.codeintel["workspace_root"] == str(root.resolve())
    assert request.route["workspace_root"] == str(root.resolve())
    assert request.codeintel["gate_input_provenance"]["target_symbol"]


def test_sprint_gate_inputs_kill_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", "0")
    request, _root = _capture_request(tmp_path, monkeypatch)
    assert dict(request.codeintel) == {}
    assert "workspace_root" not in request.route


def test_sprint_binds_the_visible_test_file_for_gate_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    bound: dict[str, Any] = {}

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        visible_verifier_unbound_reason = ""
        gate_input_test_file = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            bound["generator"] = self

        def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            raise sprint.LLMCandidateError("llm_no_patch", {"model_calls": 0})

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    root = _workspace(tmp_path)
    try:
        sprint.run_hyper_sprint(
            repo_root=root,
            config=sprint.SprintConfig(
                task=TASK,
                target_file="target.py",
                test_file="test_visible.py",
                candidate_count=1,
                llm_mode=True,
            ),
        )
    except Exception:  # noqa: BLE001 - only the binding matters here
        pass
    assert bound["generator"].gate_input_test_file == "test_visible.py"


# ---- every P16 and hard_v1 bench task (prompt-capture fairness, coordinator round 2) ----
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _p16_tasks() -> list[Any]:
    from scripts.bench.capability_ab_runner import load_tasks

    return load_tasks(_REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")


def _hard_v1_items() -> list[dict[str, Any]]:
    data_path = _REPO_ROOT / "tests" / "benchmark" / "data" / "online_ab_hard_v1_prompt_data.json"
    return list(json.loads(data_path.read_text(encoding="utf-8"))["tasks"])


def _bench_cases(tmp_path: Path) -> list[tuple[str, Path, str, str, str, list[str]]]:
    """(id, workspace, task text, source, visible test, hidden-only literals) per bench task.

    P16: the runner's own fixture materialisation (hidden test beside the visible one, as in
    the bench).  hard_v1: the committed prompt data (task text, source, visible test,
    hidden-only literal list); a sentinel test_hidden.py sits beside it.
    """

    from scripts.bench import prompt_symmetry_audit as psa
    from scripts.bench.capability_ab_runner import _materialize_fixture, _nexus_task_desc

    cases = []
    for task in _p16_tasks():
        target_file, visible_file = _materialize_fixture(tmp_path / "p16", task)
        root = Path(target_file).parent
        source = Path(target_file).read_text(encoding="utf-8")
        visible = Path(visible_file).read_text(encoding="utf-8")
        hidden = (root / "test_hidden.py").read_text(encoding="utf-8")
        material = psa.TaskMaterial(
            task_id=task.id, visible_test=visible, hidden_test=hidden, source=source
        )
        cases.append((
            task.id,
            root,
            _nexus_task_desc(task),
            source,
            visible,
            psa.hidden_only_literals(material),
        ))
    for item in _hard_v1_items():
        root = tmp_path / "hard_v1" / item["id"]
        root.mkdir(parents=True)
        (root / "target.py").write_text(item["source"], encoding="utf-8")
        (root / "test_visible.py").write_text(item["visible_test"], encoding="utf-8")
        (root / "test_hidden.py").write_text(HIDDEN, encoding="utf-8")
        cases.append((
            item["id"],
            root,
            item["task_desc"],
            item["source"],
            item["visible_test"],
            list(item["hidden_only_literals"]),
        ))
    return cases


def test_every_bench_task_strict_prompt_is_identical_and_gate_inputs_hold_no_hidden_content(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.sprint_service import _build_llm_candidate_prompt
    from scripts.bench import prompt_symmetry_audit as psa

    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    cases = _bench_cases(tmp_path)
    assert len([c for c in cases if c[0].startswith("nexus-value-")]) == 12
    assert len(cases) == 22
    for task_id, root, task, source, visible, hidden_literals in cases:
        bare_material = "\n".join([task, source, visible])
        codeintel = sprint_gate_inputs(
            repo_root=root,
            task=task,
            target_file="target.py",
            test_file="test_visible.py",
            source_code=source,
            route={"route_features": {"risk_score": 55}},
        )["codeintel"]
        blob = json.dumps(codeintel, ensure_ascii=False)
        corpus = psa.normalize(blob)
        bare_corpus = psa.normalize(bare_material)
        # Visible test only: the command names exactly test_visible.py, never the hidden test.
        assert codeintel["verify_commands"][0].endswith("-- test_visible.py"), task_id
        assert "test_hidden" not in blob, task_id
        # Same matching as the bench audit: curated literals as substrings, hidden-test string
        # constants only in quoted form.
        inventory = set(psa.HIDDEN_LITERALS.get(task_id, ())) | set(
            hidden_literals if not task_id.startswith("nexus-value-") else ()
        )
        for literal in hidden_literals:
            if literal in bare_material:
                continue  # also in what the bare arm gets
            for needle in psa._needles(literal, inventory):
                assert needle not in corpus or needle in bare_corpus, (task_id, literal)

        prompt = _build_llm_candidate_prompt(
            source_code=source, task=task, mutation_hint="baseline", test_source=visible
        )
        before, before_prompts = _run(
            root, tmp_path, feed=False, task=task, source=source, prompt=prompt
        )
        after, after_prompts = _run(
            root, tmp_path, feed=True, task=task, source=source, prompt=prompt
        )
        evaluated = [
            name
            for name in BLOCKED_BEFORE
            if name in after["capability_results"]
            and _outcome(after["capability_results"][name]).get("error") in (None, "")
        ]
        assert evaluated, task_id  # the inputs reached at least one selected gate
        assert len(before_prompts) == len(after_prompts) == 1, task_id
        assert _mask_run_identity(after_prompts[0]) == _mask_run_identity(before_prompts[0]), (
            task_id
        )
        prompt_corpus = psa.normalize(after_prompts[0])
        for literal in hidden_literals:
            if literal in bare_material:
                continue
            for needle in psa._needles(literal, inventory):
                assert needle not in prompt_corpus or needle in bare_corpus, (task_id, literal)
        assert not (root / "HIDDEN_RAN").exists(), task_id


def test_runtime_seal_vocabulary_is_known_to_the_audit_and_classifier() -> None:
    """nexus-runtime #212/#213: EVALUATED_REJECTED entries and the postflight refusal code."""

    from nexus.research.flow.unified_capability_projection import MISSING_INPUT_CODES
    from scripts.bench import prompt_symmetry_audit as psa

    assert "POSTFLIGHT_VERIFIER_PROOF_REQUIRED" in MISSING_INPUT_CODES
    schema = psa.load_block_schema()["[NEXUS CAPABILITY EVIDENCE]"]["entries[].status"]
    patterns = [re.compile(p) for p in schema["patterns"]]
    assert any(p.fullmatch("EVALUATED_REJECTED") for p in patterns)


# ---- round 2 (Gemini review of 587f63e43: H1-H3, M1-M2, L1) ----
PLAN_FIELDS = {
    "intent_pass": True,
    "target_files": ["target.py"],
    "impact_map": {"edges": [{"source": "target.py", "covered_by": "test_visible.py"}]},
    "acceptance_criteria": ["visible test test_visible.py passes"],
    "deliverables": ["target.py"],
    "steps": ["apply one model edit to target.py"],
    "handoff_readiness": 1.0,
}


def _plan_quality_probe(codeintel: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    from nexus.services.capability_registry import build_real_executor_invoker

    invoker = build_real_executor_invoker("plan_quality_gate")
    assert invoker is not None
    return dict(
        invoker({
            "task_id": "probe",
            "task_statement": TASK,
            "codeintel": codeintel,
            "route": route,
            "planner": {},
        })
    )


def test_h1_plan_quality_risk_comes_only_from_route_features_for_gate_inputs() -> None:
    fed = {**PLAN_FIELDS, "risk_score": 99, "gate_input_provenance": {"intent_pass": "x"}}
    # codeintel.risk_score is ignored for gate inputs: without a route risk the gate refuses.
    refused = _plan_quality_probe(fed, {})
    outcome = refused["response"]["outcome"]
    assert outcome["error"] == "PLAN_QUALITY_CONTEXT_REQUIRED"
    assert outcome["missing_inputs"] == ["risk_score"]
    evaluated = _plan_quality_probe(fed, {"route_features": {"risk_score": 55}})
    assert evaluated["response"]["outcome"]["semantic_status"] == "SUCCEEDED"
    # Callers that seed the plan context directly in codeintel (wiring audit fixture, family
    # canary; no gate_input_provenance) keep their behaviour.
    legacy = _plan_quality_probe({**PLAN_FIELDS, "risk_score": 10}, {})
    assert legacy["response"]["outcome"]["semantic_status"] == "SUCCEEDED"


def test_h1_gate_inputs_never_carry_codeintel_summary_fields(tmp_path: Path) -> None:
    from nexus.research.gate_inputs import FORBIDDEN_CODEINTEL_KEYS

    root = _workspace(tmp_path)
    codeintel = sprint_gate_inputs(
        repo_root=root,
        task=TASK,
        target_file="target.py",
        test_file="test_visible.py",
        route={"route_features": {"risk_score": 55}, "risk_score": 55},
    )["codeintel"]
    assert not FORBIDDEN_CODEINTEL_KEYS & set(codeintel)


@pytest.mark.parametrize(
    "path",
    ["test_hidden/test_cases.py", "tests/hidden_test.py", "Hidden/test_x.py", "x/HIDDEN.py"],
)
def test_h2_any_hidden_path_component_is_refused(tmp_path: Path, path: str) -> None:
    from nexus.research.sprint_service import visible_test_target_error

    root = _workspace(tmp_path)
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(VISIBLE, encoding="utf-8")
    assert visible_test_target_error(root, path) == "hidden_test_target"
    codeintel = sprint_gate_inputs(
        repo_root=root, task=TASK, target_file="target.py", test_file=path
    )["codeintel"]
    assert "verify_commands" not in codeintel


def test_h2_only_the_registered_visible_test_and_no_symlinked_directory(tmp_path: Path) -> None:
    from nexus.research.sprint_service import visible_test_target_error

    root = _workspace(tmp_path)
    (root / "test_other.py").write_text(VISIBLE, encoding="utf-8")
    other = sprint_gate_inputs(
        repo_root=root,
        task=TASK,
        target_file="target.py",
        test_file="test_other.py",
        registered_test_file="test_visible.py",
    )["codeintel"]
    assert "verify_commands" not in other
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "test_v.py").write_text(VISIBLE, encoding="utf-8")
    (root / "linked").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert visible_test_target_error(root, "linked/test_v.py") == "test_file_is_symlink"
    assert visible_test_target_error(root, "linked") != ""  # never a directory


def _hostile_workspace(tmp_path: Path) -> Path:
    root = _workspace(tmp_path)
    (root / "pytest.ini").write_text("[pytest]\naddopts = test_hidden.py\n", encoding="utf-8")
    (root / "conftest.py").write_text(
        "from pathlib import Path\nPath(__file__).with_name('CONFTEST_RAN').write_text('x')\n",
        encoding="utf-8",
    )
    return root


def test_h3_pregate_ignores_workspace_pytest_config_and_conftest(
    governed_admission: None, tmp_path: Path
) -> None:
    root = _hostile_workspace(tmp_path)
    after, _ = _run(root, tmp_path, feed=True)
    pregate = _outcome(after["capability_results"]["pregate"])
    assert pregate["command_count"] == 1
    result = pregate["results"][0]
    assert "--noconftest" in result["cmd"] and f"-c {os.devnull}" in result["cmd"]
    assert result["cmd"].endswith("-- test_visible.py")
    assert "1 failed" in result["stdout_tail"]  # the visible test ran (and fails here)
    assert not (root / "HIDDEN_RAN").exists()
    assert not (root / "CONFTEST_RAN").exists()


def test_h3_pregate_inside_bench_staging_cannot_see_the_hidden_test(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.bench import hidden_test_staging as staging_mod

    monkeypatch.setattr(staging_mod, "_STAGING_PARENT", tmp_path / "cache" / "hidden")
    for name in ("_ACTIVE", "_RUN_ROOTS", "_IN_MEMORY_SHAS"):
        monkeypatch.setattr(staging_mod, name, {})
    monkeypatch.setattr(staging_mod, "_QUARANTINED", set())
    monkeypatch.setattr(staging_mod, "_RUN_ABORT", [])
    monkeypatch.setattr(staging_mod, "_RUN_RECORD_PATH", [])
    root = _hostile_workspace(tmp_path)
    with staging_mod.staged_hidden_test(
        enabled=True,
        repo_root=root,
        test_file=str(root / "test_visible.py"),
        task_id="gate-inputs",
        trial_index=1,
    ) as staging:
        assert staging is not None and not (root / "test_hidden.py").exists()
        after, _ = _run(root, tmp_path, feed=True)
        assert staging.check_absent("after_pregate")
    pregate = _outcome(after["capability_results"]["pregate"])
    assert pregate["command_count"] == 1 and "1 failed" in pregate["results"][0]["stdout_tail"]
    assert not (root / "HIDDEN_RAN").exists() and (root / "test_hidden.py").exists()
    assert not staging.violations
    # The staging tree is mode 0300/0000 by design; make it removable for tmp_path cleanup.
    pending = [tmp_path / "cache"]
    while pending:
        current = pending.pop()
        if current.is_symlink():
            continue
        if current.is_dir():
            current.chmod(0o700)  # first, so the directory can be listed
            pending.extend(current.iterdir())
        else:
            current.chmod(0o600)


def test_m1_withhold_covers_the_mempalace_registry_alias() -> None:
    from nexus.research.gate_inputs import fed_capability_names
    from nexus.services.online_nexus_context import withhold_fed_gate_verdicts

    assert "mempalace" in fed_capability_names()
    out = withhold_fed_gate_verdicts({
        "entries": [
            {
                "name": "mempalace",
                "status": "REAL_INVOKED",
                "success": True,
                "invoked_real": True,
                "consumer_payload": {"fields": {"hit_count": 1}},
                "has_consumer_payload": True,
            }
        ]
    })
    assert out["entries"][0]["status"] == "INVOKED_NOT_SUCCESS"
    assert out["entries"][0]["consumer_payload"] == {}


def test_m2_symlinked_or_escaping_target_is_not_a_target(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (tmp_path / "outside.py").write_text(ORIGINAL, encoding="utf-8")
    (root / "link.py").symlink_to(tmp_path / "outside.py")
    (tmp_path / "outdir").mkdir()
    (tmp_path / "outdir" / "t.py").write_text(ORIGINAL, encoding="utf-8")
    (root / "pkg").symlink_to(tmp_path / "outdir", target_is_directory=True)
    for target in ("link.py", "pkg/t.py", "../outside.py", str(tmp_path / "outside.py")):
        codeintel = sprint_gate_inputs(
            repo_root=root, task=TASK, target_file=target, test_file="test_visible.py"
        )["codeintel"]
        assert "target_file" not in codeintel and codeintel["intent_pass"] is False, target


def test_l1_non_fed_evaluated_rejected_entry_drops_its_payload() -> None:
    from nexus.services.online_nexus_context import withhold_fed_gate_verdicts

    out = withhold_fed_gate_verdicts({
        "entries": [
            {
                "name": "research",
                "status": "EVALUATED_REJECTED",
                "success": True,
                "invoked_real": True,
                "consumer_payload": {"fields": {"hit_count": 1}},
                "has_consumer_payload": True,
            }
        ]
    })
    entry = out["entries"][0]
    assert entry["status"] == "INVOKED_NOT_SUCCESS" and entry["consumer_payload"] == {}
    assert entry["success"] is False and entry["invoked_real"] is False
    assert entry["has_consumer_payload"] is False


# ---- round 3 (independent review of 050dd62bb) ----
def test_absolute_in_repo_paths_are_normalised_like_the_counted_runner_passes_them(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    codeintel = sprint_gate_inputs(
        repo_root=root,
        task=TASK,
        target_file=str(root / "target.py"),
        test_file=str(root / "test_visible.py"),
        registered_test_file=str(root / "test_visible.py"),
        route={"route_features": {"risk_score": 55}},
    )["codeintel"]
    assert codeintel["target_file"] == "target.py"
    assert codeintel["verify_commands"][0].endswith("-- test_visible.py")
    assert codeintel["intent_pass"] is True and codeintel["handoff_readiness"] == 1.0
    assert codeintel["target_symbol"] == "remaining_ms"
    # An absolute path outside the repo is refused, never normalised.
    (tmp_path / "test_out.py").write_text(VISIBLE, encoding="utf-8")
    outside = sprint_gate_inputs(
        repo_root=root,
        task=TASK,
        target_file=str(tmp_path / "test_out.py"),
        test_file=str(tmp_path / "test_out.py"),
    )["codeintel"]
    assert "verify_commands" not in outside and "target_file" not in outside


def test_repo_relative_path_refuses_outside_and_symlinked_absolute_paths(tmp_path: Path) -> None:
    from nexus.research.sprint_service import repo_relative_path

    root = _workspace(tmp_path)
    assert repo_relative_path(root, str(root / "test_visible.py")) == ("test_visible.py", "")
    assert repo_relative_path(root, str(root.resolve() / "test_visible.py"))[0] == (
        "test_visible.py"
    )
    assert repo_relative_path(root, str(tmp_path / "x.py"))[1] == "path_outside_repo"
    assert repo_relative_path(root, str(root / ".." / "x.py"))[1] == "path_outside_repo"
    (tmp_path / "d").mkdir()
    (root / "ln").symlink_to(tmp_path / "d", target_is_directory=True)
    assert repo_relative_path(root, str(root / "ln" / "t.py"))[1] == "path_has_symlink"


def test_sprint_binds_the_relative_visible_test_from_absolute_config_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.sprint_service as sprint

    bound: dict[str, Any] = {}

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        visible_verifier_unbound_reason = ""
        gate_input_test_file = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            bound["generator"] = self

        def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            raise sprint.LLMCandidateError("llm_no_patch", {"model_calls": 0})

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    root = _workspace(tmp_path)
    try:
        sprint.run_hyper_sprint(
            repo_root=root,
            config=sprint.SprintConfig(
                task=TASK,
                target_file=str(root / "target.py"),
                test_file=str(root / "test_visible.py"),
                candidate_count=1,
                llm_mode=True,
            ),
        )
    except Exception:  # noqa: BLE001 - only the binding matters here
        pass
    generator = bound["generator"]
    assert generator.gate_input_test_file == "test_visible.py"
    # #2212's verifier target check sees the normalised path too (no longer "not relative").
    assert generator.visible_test_target_invalid == ""


@pytest.mark.parametrize("task_id", ["nexus-value-hidden-001", "nexus-value-hidden-002"])
def test_p16_hidden_named_task_directories_keep_their_visible_test(
    tmp_path: Path, task_id: str
) -> None:
    from nexus.research.sprint_service import visible_test_target_error

    root = _workspace(tmp_path)
    rel = f".nexus/bench_cases/{task_id}/test_visible.py"
    (root / rel).parent.mkdir(parents=True)
    (root / rel).write_text(VISIBLE, encoding="utf-8")
    assert visible_test_target_error(root, rel) == ""
    codeintel = sprint_gate_inputs(
        repo_root=root, task=TASK, target_file="target.py", test_file=rel
    )["codeintel"]
    assert codeintel["verify_commands"][0].endswith(f"-- {rel}")


@pytest.mark.parametrize("raw", ["true", "on", "yes", "2", ""])
def test_gate_inputs_kill_switch_is_fail_closed(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from nexus.research.gate_inputs import gate_inputs_enabled

    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", raw)
    with pytest.raises(ValueError):
        gate_inputs_enabled()
    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", "0")
    assert gate_inputs_enabled() is False
    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", "1")
    assert gate_inputs_enabled() is True
    monkeypatch.delenv("NEXUS_SPRINT_GATE_INPUTS")
    assert gate_inputs_enabled() is True


def test_strict_lane_feeds_no_gate_inputs_because_model_context_would_carry_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR-5a: the strict lane is fed only when the runtime honours receipt-only evidence; on an
    older runtime it falls back to design A (no inputs), because [NEXUS MODEL CONTEXT] would
    carry the passing gates' evidence ids and payloads (round-3 counted-shape proof)."""

    from nexus.research import gate_inputs

    monkeypatch.delenv("NEXUS_SPRINT_GATE_INPUTS", raising=False)
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    for name in ("old", "new", "fed"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(gate_inputs, "runtime_supports_receipt_only", lambda: False)
    strict_old, _root = _capture_request(tmp_path / "old", monkeypatch)
    assert dict(strict_old.codeintel) == {} and "workspace_root" not in strict_old.route
    assert strict_old.route["receipt_only_capabilities"]  # declared either way
    monkeypatch.setattr(gate_inputs, "runtime_supports_receipt_only", lambda: True)
    strict_new, _root = _capture_request(tmp_path / "new", monkeypatch)
    assert strict_new.codeintel["verify_commands"]
    assert strict_new.route["receipt_only_capabilities"] == sorted(
        gate_inputs.fed_capability_names()
    )
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT")
    fed, _root = _capture_request(tmp_path / "fed", monkeypatch)
    assert fed.codeintel["verify_commands"]


def test_baseline_path_binds_the_task_files_for_gate_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.app import research_flow_service as rfs
    from nexus.research.sprint_service import LLMCandidateGenerator

    root = _workspace(tmp_path)
    gen = LLMCandidateGenerator(root, safe_mode=True)
    rfs._bind_gate_input_files(
        gen, root, target_file=str(root / "target.py"), test_file=str(root / "test_visible.py")
    )
    assert gen.gate_input_target_file == "target.py"
    assert gen.gate_input_test_file == "test_visible.py"
    assert gen.target_file == ""  # never enables a Local assist request
    rfs._bind_gate_input_files(gen, root, target_file="target.py", test_file="test_hidden.py")
    assert gen.gate_input_test_file == ""


# ---- round 4 (nexus-runtime #217 receipt-only rendering) ----
def _fed_entry(status: str, refs: list[str], *, success: bool = False) -> dict[str, Any]:
    return {
        "name": "pregate",
        "status": status,
        "success": success,
        "invoked_real": success,
        "invoked_stub": False,
        "skipped": False,
        "evidence_ids": refs,
        "evidence_refs": refs,
        "runtime_evidence_ids": [f"rt:output:pregate:sha256:{'a' * 64}"],
        "physical_callable": "capability_executor_registry:pregate",
        "consumer_payload": {"fields": {"all_passed": success}} if success else {},
        "has_consumer_payload": success,
    }


def test_fed_entry_renders_one_opaque_placeholder_for_pass_blocked_and_rejected() -> None:
    """Outcome-bearing refs must not survive; an id shared with a visible entry must stay."""

    from nexus.services.online_nexus_context import (
        compact_capability_evidence_for_prompt,
        withhold_fed_gate_verdicts,
    )

    shared = "ev_shared_bundle_seed"
    learn = {
        "name": "learn_mode",
        "status": "REAL_INVOKED",
        "success": True,
        "invoked_real": True,
        "evidence_ids": ["ev_learn_1", shared],
        "physical_callable": "capability_executor_registry:learn_mode",
    }
    fed_variants = [
        _fed_entry("REAL_INVOKED", ["ev_pregate_execution_t", shared], success=True),
        _fed_entry("INVOKED_NOT_SUCCESS", ["ev_pregate_blocked_t"]),
        _fed_entry("EVALUATED_REJECTED", ["ev_cap_pregate_1234abcd"]),
        {"name": "pregate", "status": "SELECTED_NOT_EXECUTED", "evidence_ids": []},
        {"name": "pregate", "status": "PENDING_OR_STAGE_OWNED", "evidence_ids": []},
    ]
    views = []
    for entry in fed_variants:
        top = [*entry.get("evidence_ids", []), "ev_learn_1", shared]
        bundle = {
            "schema": "nexus.capability_evidence_bundle.v1",
            "bundle_hash": "b" * 64,
            "baseline_hash": "c" * 64,
            "entries": [entry, learn],
            "evidence_ids": list(dict.fromkeys(top)),
        }
        withheld = withhold_fed_gate_verdicts(bundle)
        assert withheld["evidence_ids"] == ["ev_learn_1", shared]
        view = json.dumps(compact_capability_evidence_for_prompt(withheld), sort_keys=True)
        assert "pregate_" not in view and "rt:output" not in view
        views.append(view)
    # Identical text for passed / blocked / rejected / not run (fixed hashes: nothing masked).
    assert len(set(views)) == 1


def test_strict_route_names_the_receipt_only_capabilities_and_the_pinned_runtime_accepts_it(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.gate_inputs import fed_capability_names

    monkeypatch.delenv("NEXUS_SPRINT_GATE_INPUTS", raising=False)
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    (tmp_path / "cap").mkdir()
    request, _root = _capture_request(tmp_path / "cap", monkeypatch)
    assert request.route["receipt_only_capabilities"] == sorted(fed_capability_names())
    root = _workspace(tmp_path)
    plain, plain_prompts = _run(root, tmp_path, feed=False)
    keyed, keyed_prompts = _run(
        root,
        tmp_path,
        feed=True,
        extra_route={"receipt_only_capabilities": sorted(fed_capability_names())},
    )
    assert keyed["online"]["status"] == plain["online"]["status"]
    assert _mask_run_identity(keyed_prompts[0]) == _mask_run_identity(plain_prompts[0])
    # The pinned runtime acts on the key: every fed gate's entry is sealed receipt-only.
    sealed = {e["name"]: e for e in keyed["capability_evidence_bundle"]["entries"]}
    for name in FED_CAPABILITIES:
        entry = sealed.get(name) or sealed.get("mempalace" if name == "mempalace_gate" else "")
        assert entry is not None and entry.get("consumer_visibility") == "receipt_only", name
    assert all(
        "consumer_visibility" not in e for e in plain["capability_evidence_bundle"]["entries"]
    )


def test_misspelt_kill_switch_is_ignored_in_the_strict_lane_and_refused_by_the_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from scripts.bench import capability_ab_runner as runner

    monkeypatch.setenv("NEXUS_SPRINT_GATE_INPUTS", "yes")
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    request, _root = _capture_request(tmp_path, monkeypatch)  # strict lane: never parsed
    assert dict(request.codeintel) == {}
    # The runner refuses to start (argparse error, exit 2) before doing anything else.
    monkeypatch.setattr(sys, "argv", ["capability_ab_runner.py", "--preflight-only"])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert "NEXUS_SPRINT_GATE_INPUTS must be 0 or 1" in capsys.readouterr().err


def test_visibility_flag_alone_is_not_physical_output() -> None:
    from nexus.research.flow.unified_capability_projection import _physical_output

    record = {
        "status": "SUCCEEDED",
        "consumer_visibility": "receipt_only",
        "response": {
            "status": "SUCCEEDED",
            "consumer_visibility": "receipt_only",
            "outcome": {"semantic_status": "SUCCEEDED", "consumer_visibility": "receipt_only"},
        },
    }
    assert _physical_output(record) is False
    record["response"]["outcome"]["result"] = {"hit_count": 2}
    assert _physical_output(record) is True


def test_pinned_runtime_supports_receipt_only_and_detection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    assert _detect_receipt_only() is True  # pin e73d152f1 (nexus-runtime #217)
    import importlib

    bundle = importlib.import_module("nexus_runtime.planning.services.capability_evidence_bundle")

    monkeypatch.setattr(bundle, "RECEIPT_ONLY_ROUTE_KEY", "other_key")
    assert _detect_receipt_only() is False
    monkeypatch.undo()
    monkeypatch.delattr(bundle, "receipt_only_capability_names")
    assert _detect_receipt_only() is False
    monkeypatch.undo()
    # An older pin without the module at all: import failure means no support.
    real_import = builtins.__import__

    def no_bundle(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("nexus_runtime.planning.services"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    def no_module(name: str, *args: Any, **kwargs: Any) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(builtins, "__import__", no_bundle)
    monkeypatch.setattr(importlib, "import_module", no_module)
    assert _detect_receipt_only() is False


# --- Boundary tests: the receipt-only declaration really keeps the fed gates out of the
# model-facing ``[NEXUS MODEL CONTEXT]`` block.  Nexus-new builds its runtime with
# ``online_context_projection=False``, so ``_run`` alone never renders that block; these
# tests wrap the online invoker with the pinned runtime's ``wrap_online_invoker`` (the
# projection the original leak went through).
_LEAK_MARKERS = ("capability_wired", "cost_lane", "ev_cap_")
_MODEL_CONTEXT_MARKER = "[NEXUS MODEL CONTEXT]"
_TIMESTAMP = re.compile(r'"timestamp":\s*"[^"]*"')


# The 64-hex values that differ fed vs unfed in the strict model context are exactly the
# hashes the runtime computes over the whole sealed bundle: ``bundle_hash`` (also rendered as
# ``capability-evidence:<h>``), ``consumer_projection_hash`` and ``package_hash``.  They are
# opaque SHA-256 digests over content that INCLUDES the receipt-only entries (gate outcomes)
# and, in other lanes, the per-run random ``ev_cap_*`` ids, so they are not pure run noise.
# They are masked here; hashing only the model-visible projection is nexus-runtime #220.
_BUNDLE_CONTENT_HASH_KEYS = (
    '"bundle_hash":"',
    '"capability-evidence:',
    '"consumer_projection_hash":"',
    '"package_hash":"',
)


def _mask_projection_noise(prompt: str) -> str:
    """Only three classes are masked: random ``ev_cap_*`` ids, the learn-mode timestamp and
    64-hex content hashes (see ``_BUNDLE_CONTENT_HASH_KEYS``)."""

    return _TIMESTAMP.sub('"timestamp": "<t>"', _mask_run_identity(prompt))


def _strict_fed_and_unfed_model_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, dict[str, Any], str, str, dict[str, Any]]:
    """Strict lane through the sprint's own request assembly (which declares the
    receipt-only capabilities) and the runtime's model-context projection; returns
    ``(fed_request, fed_receipt, fed_prompt, unfed_prompt, fed_codeintel)``."""

    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    root = _workspace(tmp_path)
    _install_target_python(root)
    (tmp_path / "fed").mkdir()
    (tmp_path / "unfed").mkdir()
    fed_request, fed, fed_prompts = _sprint_run(
        root, tmp_path / "fed", monkeypatch, feed=True, model_context=True
    )
    _unfed_request, _unfed, unfed_prompts = _sprint_run(
        root, tmp_path / "unfed", monkeypatch, feed=False, model_context=True
    )
    assert len(fed_prompts) == len(unfed_prompts) == 1
    return fed_request, fed, fed_prompts[0], unfed_prompts[0], dict(fed_request.codeintel)


def test_strict_model_context_is_identical_fed_and_unfed_and_carries_no_gate_input(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.gate_inputs import fed_capability_names

    request, fed, fed_prompt, unfed_prompt, codeintel = _strict_fed_and_unfed_model_context(
        tmp_path, monkeypatch
    )
    # (a) The sprint itself declared the receipt-only capabilities on the request route.
    assert request.route["receipt_only_capabilities"] == sorted(fed_capability_names())
    # The projection really ran (otherwise the comparison below proves nothing).
    assert _MODEL_CONTEXT_MARKER in fed_prompt and _MODEL_CONTEXT_MARKER in unfed_prompt
    assert _mask_projection_noise(fed_prompt) == _mask_projection_noise(unfed_prompt)
    # Unmasked, the only differing tokens are the bundle-content hashes (nexus-runtime #220):
    # every other 64-hex value, and all text between the hex values, is byte-identical.
    fed_hex, unfed_hex = list(_HEX.finditer(fed_prompt)), list(_HEX.finditer(unfed_prompt))
    assert _HEX.split(fed_prompt) == _HEX.split(unfed_prompt)
    assert len(fed_hex) == len(unfed_hex)
    differing = [f for f, u in zip(fed_hex, unfed_hex) if f.group() != u.group()]
    for match in differing:
        before = fed_prompt[: match.start()]
        assert before.endswith(_BUNDLE_CONTENT_HASH_KEYS), before[-60:]
    # The six fed gates evaluated and were sealed receipt-only.
    entries = {e["name"]: e for e in fed["capability_evidence_bundle"]["entries"]}
    for name in FED_CAPABILITIES:
        entry = entries.get(name) or entries.get("mempalace" if name == "mempalace_gate" else "")
        assert entry is not None, name
        assert entry.get("consumer_visibility") == "receipt_only", name
        assert entry["status"] != "SELECTED_NOT_EXECUTED", name
    # None of the fed input values reaches the model.
    fed_values = [
        codeintel["workspace_root"],
        *codeintel["verify_commands"],
        codeintel["target_symbol"],
        codeintel["mempalace_artifact"]["artifact_id"],
        codeintel["mempalace_artifact"]["visible_test_sha256"],
        *codeintel["steps"],
        *codeintel["acceptance_criteria"],
    ]
    for value in filter(None, fed_values):
        assert value not in fed_prompt, value
    for key in ("target_file", "target_files", "target_symbol"):
        assert key not in fed_prompt, key
    for marker in _LEAK_MARKERS:
        assert marker not in fed_prompt, marker


def test_strict_model_context_differs_when_the_runtime_ignores_the_declaration(
    governed_admission: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: a runtime that ignores ``receipt_only_capabilities`` leaks the
    fed gates into the model context, and the comparison above catches it."""

    import nexus_runtime.kernel.unified_runtime as unified_runtime

    from nexus.research import gate_inputs

    monkeypatch.setattr(
        unified_runtime, "resolve_receipt_only_capabilities", lambda _route: (frozenset(), None)
    )
    # The behavioural detection would now (rightly) refuse to feed the strict lane; force the
    # old names-only answer so the sprint feeds a runtime that ignores the declaration.
    monkeypatch.setattr(gate_inputs, "runtime_supports_receipt_only", lambda: True)
    _request, fed, fed_prompt, unfed_prompt, _codeintel = _strict_fed_and_unfed_model_context(
        tmp_path, monkeypatch
    )
    assert _MODEL_CONTEXT_MARKER in fed_prompt
    assert all(
        e.get("consumer_visibility") != "receipt_only"
        for e in fed["capability_evidence_bundle"]["entries"]
    )
    assert _mask_projection_noise(fed_prompt) != _mask_projection_noise(unfed_prompt)
    assert len(fed_prompt) > len(unfed_prompt)
    for marker in ("capability_wired", "ev_cap_"):
        assert marker in fed_prompt and marker not in unfed_prompt, marker


def test_receipt_only_detection_is_behavioural_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Names and constants are not enough: a runtime whose route resolution or projection
    ignores the declaration is reported unsupported, and so is any runtime error."""

    import importlib

    import nexus_runtime.kernel.unified_runtime as unified_runtime
    import nexus_runtime.task_context.consumer_projection as projection

    assert _detect_receipt_only() is True  # real pin: projection hides the entry
    # Route resolution ignores the key (contract names unchanged).
    monkeypatch.setattr(
        unified_runtime, "resolve_receipt_only_capabilities", lambda _route: (frozenset(), None)
    )
    assert _detect_receipt_only() is False
    monkeypatch.undo()
    # The entry is sealed receipt-only but the projection renders it anyway.
    monkeypatch.setattr(projection, "entry_prompt_visible", lambda _entry: True)
    assert _detect_receipt_only() is False
    monkeypatch.undo()

    # Evidence ids hidden, but the projection still renders the receipt-only payload.
    real_build = projection.build_online_context_package

    def leaks_payload(context: Any) -> dict[str, Any]:
        package = dict(real_build(context))
        package["leaked_payloads"] = [
            e.get("consumer_payload") for e in context["capability_evidence_bundle"]["entries"]
        ]
        return package

    monkeypatch.setattr(projection, "build_online_context_package", leaks_payload)
    assert _detect_receipt_only() is False
    monkeypatch.undo()

    # Projection raises: fail closed.
    def broken(_context: Any) -> dict[str, Any]:
        raise RuntimeError("projection unavailable")

    monkeypatch.setattr(projection, "build_online_context_package", broken)
    assert _detect_receipt_only() is False
    monkeypatch.undo()
    # The projection module (or the kernel) cannot be imported: fail closed.
    real_import_module = importlib.import_module

    def no_projection(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {
            "nexus_runtime.task_context.consumer_projection",
            "nexus_runtime.kernel.unified_runtime",
        }:
            raise ImportError(name)
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", no_projection)
    assert _detect_receipt_only() is False
    monkeypatch.undo()
    assert _detect_receipt_only() is True
