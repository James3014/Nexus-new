"""Wiring plan PR-1: the sprint's runtime verifier stage carries visible-test proof.

Before, the verifier stage only checked that an online payload existed, so the runtime
postflight artifact/claim/delivery gates blocked every row with
``missing_verifier_artifact`` / ``missing_verifier_source_hash``.  The verifier now applies the
online candidate, runs the sprint's visible-test evaluator (never the hidden test) and binds
the candidate sha256 and the sealed source hash.

Hermetic: the gateway's ``ask_unified`` is replaced by a stand-in that drives the verifier
callback the way UnifiedRuntime does (online stage, sealed ``source_hash``, execution attempt
in the context), and the returned verifier stage is fed to the real postflight gate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nexus.research.sprint_service import CandidateEval, LLMCandidateGenerator
from nexus.services.online_nexus_context import evaluate_postflight_gate

SOURCE = "def normalize(text):\n    return text\n"
CANDIDATE = "def normalize(text):\n    return text.strip()\n"
EDIT = {
    "status": "APPROVED",
    "operation": "replace",
    "target_snippet": "return text",
    "replacement": "return text.strip()",
}
SEALED_SOURCE = "a" * 64
GATES = ("artifact_gate", "claim_gate", "delivery_gate")


def _run(tmp_path: Path, *, visible_score: float | None) -> tuple[dict[str, Any], list[str]]:
    """Drive one online candidate through the verifier; return the postflight context."""

    seen: list[str] = []
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-001"
    if visible_score is not None:

        def visible(code: str, seed: int) -> CandidateEval:
            seen.append(code)
            return CandidateEval(seed=seed, score=visible_score, candidate_code=code)

        generator.visible_verifier = visible
    captured: dict[str, Any] = {}

    def ask_unified(request: Any, *, verifier: Any = None, **_kwargs: Any) -> dict[str, Any]:
        online = {
            "name": "online",
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"response": json.dumps(EDIT), "raw_response": json.dumps(EDIT)},
        }
        context: dict[str, Any] = {
            "task_id": request.task_id,
            "online": online,
            "source_hash": SEALED_SOURCE,
            "execution_attempt": {"attempt_id": "attempt-1"},
        }
        payload = dict(verifier(context))
        passed = bool(payload.get("gate_passed", payload.get("status") == "pass"))
        # Same stage shape UnifiedRuntime._run_callback builds.
        context["verifier"] = {
            "name": "verifier",
            "status": "SUCCEEDED" if passed else "FAILED",
            "invoked": True,
            "gate_passed": passed,
            "evidence_refs": list(payload.get("evidence_refs") or []),
            "response": payload,
        }
        captured["context"] = context
        return {"task_id": request.task_id, "online": online, "verifier": context["verifier"]}

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    out, _raw, _receipt = generator._ask_unified_candidate(
        prompt="fix normalize",
        payload="Return one small edit.",
        task="fix normalize",
        seed=1,
        attempt=1,
        model="m",
        source_code=SOURCE,
    )
    assert out["candidate_response_path"] == "operation_json"
    return captured["context"], seen


def _gates(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: evaluate_postflight_gate(name, context) for name in GATES}


def test_passing_visible_test_binds_candidate_sha_and_passes_postflight_gates(
    tmp_path: Path,
) -> None:
    context, seen = _run(tmp_path, visible_score=1.0)

    assert seen == [CANDIDATE]  # the visible evaluator saw exactly the applied online candidate
    response = context["verifier"]["response"]
    sha = hashlib.sha256(CANDIDATE.encode("utf-8")).hexdigest()
    assert response["verifier_status"] == "pass"
    assert response["visible_test_passed"] is True
    assert response["verifier_artifact"] == f"sha256:{sha}"
    assert response["candidate_hash"] == sha
    assert response["source_hash"] == SEALED_SOURCE
    assert response["attempt_id"] == "attempt-1"
    assert context["verifier"]["gate_passed"] is True
    for name, verdict in _gates(context).items():
        assert verdict["gate_passed"] is True, (name, verdict["blockers"])


def test_failing_visible_test_fails_verifier_and_blocks_postflight_gates(tmp_path: Path) -> None:
    context, seen = _run(tmp_path, visible_score=0.4)

    assert seen == [CANDIDATE]
    response = context["verifier"]["response"]
    assert response["verifier_status"] == "fail"
    assert response["visible_test_passed"] is False
    assert response["verifier_artifact"].startswith("sha256:")
    assert context["verifier"]["gate_passed"] is False
    for name, verdict in _gates(context).items():
        assert verdict["gate_passed"] is False
        # Blocked by the real failing verdict, not by missing proof.
        assert "missing_verifier_artifact" not in verdict["blockers"]
        assert "verifier_status_fail" in verdict["blockers"], (name, verdict["blockers"])


def test_without_visible_evaluator_the_verifier_claims_no_test_proof(tmp_path: Path) -> None:
    context, seen = _run(tmp_path, visible_score=None)

    assert seen == []
    response = context["verifier"]["response"]
    assert "verifier_status" not in response
    assert "verifier_artifact" not in response
    # Codex #2212 F4: a delivered payload with nothing tested is never "pass".
    assert response["status"] == "no_verifier"
    assert response["gate_passed"] is False
    assert context["verifier"]["gate_passed"] is False
    for verdict in _gates(context).values():
        assert verdict["gate_passed"] is False


def test_visible_test_target_must_be_one_regular_non_hidden_file(tmp_path: Path) -> None:
    from nexus.research.sprint_service import visible_test_pytest_cmd, visible_test_target_error

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_visible.py").write_text("def test_ok():\n    pass\n")
    (tmp_path / "tests" / "test_hidden.py").write_text("def test_secret():\n    pass\n")

    assert visible_test_target_error(tmp_path, "tests/test_visible.py") == ""
    assert visible_test_target_error(tmp_path, "") == "missing_test_file"
    assert visible_test_target_error(tmp_path, "tests") == "test_file_not_python"
    (tmp_path / "suite.py").mkdir()
    assert visible_test_target_error(tmp_path, "suite.py") == "test_file_not_regular_file"
    assert visible_test_target_error(tmp_path, "tests/test_hidden.py") == "hidden_test_target"
    assert visible_test_target_error(tmp_path, "../x/test_a.py") == "test_file_not_repo_relative"
    assert visible_test_target_error(tmp_path, str(tmp_path / "tests" / "test_visible.py")) == (
        "test_file_not_repo_relative"
    )
    cmd = visible_test_pytest_cmd("tests/test_visible.py")
    assert cmd[1:] == ["-m", "pytest", "-q", "--maxfail=1", "--", "tests/test_visible.py"]
    # Gemini G10: an option-like name is never a target (and ``--`` ends options anyway).
    (tmp_path / "-k.py").write_text("def test_x():\n    pass\n")
    (tmp_path / "-sub").mkdir()
    (tmp_path / "-sub" / "test_a.py").write_text("def test_x():\n    pass\n")
    assert visible_test_target_error(tmp_path, "-k.py") == "test_file_option_like"
    assert visible_test_target_error(tmp_path, "-sub/test_a.py") == "test_file_option_like"


def test_invalid_visible_target_fails_closed_without_running(tmp_path: Path) -> None:
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-003"
    generator.visible_test_target_invalid = "hidden_test_target"
    captured: dict[str, Any] = {}

    def ask_unified(request: Any, *, verifier: Any = None, **_kwargs: Any) -> dict[str, Any]:
        online = {
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"response": json.dumps(EDIT), "raw_response": ""},
        }
        captured["payload"] = dict(
            verifier({"task_id": request.task_id, "online": online, "source_hash": SEALED_SOURCE})
        )
        return {"task_id": request.task_id, "online": online}

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    generator._ask_unified_candidate(
        prompt="p", payload="x", task="t", seed=1, attempt=1, model="m", source_code=SOURCE
    )
    payload = captured["payload"]
    assert payload["verifier_status"] == "visible_test_target_invalid"
    assert payload["gate_passed"] is False
    assert payload["invoked"] is False and payload["evidence_refs"] == []  # nothing ran
    assert "verifier_artifact" not in payload
    context = {
        "task_id": payload["task_id"],
        "source_hash": SEALED_SOURCE,
        "verifier": {"invoked": True, "gate_passed": False, "response": payload},
    }
    assert all(not verdict["gate_passed"] for verdict in _gates(context).values())


def test_sprint_binds_no_visible_verifier_without_a_valid_test_file(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import nexus.research.sprint_service as sprint

    bound: dict[str, Any] = {}

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            bound["generator"] = self

        def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            raise sprint.LLMCandidateError("llm_no_patch", {"model_calls": 0})

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    (tmp_path / "demo.py").write_text(SOURCE)
    (tmp_path / "test_hidden.py").write_text("def test_secret():\n    assert False\n")
    for test_file, reason in (("", "missing_test_file"), ("test_hidden.py", "hidden_test_target")):
        bound.clear()
        try:
            sprint.run_hyper_sprint(
                repo_root=tmp_path,
                config=sprint.SprintConfig(
                    task="fix normalize",
                    target_file="demo.py",
                    test_file=test_file,
                    candidate_count=1,
                    llm_mode=True,
                ),
            )
        except Exception:  # noqa: BLE001 - only the binding matters here
            pass
        generator = bound["generator"]
        assert generator.visible_verifier is None
        assert generator.visible_test_target_invalid == reason


def test_memo_hit_and_miss_give_the_sprint_the_same_visible_evaluation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """M3: the verifier runs the sprint's exact pytest command, so the self-heal input
    (candidate stdout) is the same whether the sprint reuses the verifier's run or not."""

    import re

    import nexus.research.sprint_service as sprint

    (tmp_path / "demo.py").write_text(SOURCE)
    (tmp_path / "test_demo.py").write_text(
        "from demo import normalize\n\n"
        "def test_a():\n    assert normalize(' x ') == 'X'\n\n"
        "def test_b():\n    assert normalize('y') == 'Y'\n"
    )
    seen: dict[str, Any] = {}

    def make_generator(call_verifier: bool) -> type:
        class _Generator:
            visible_verifier = None
            visible_test_target_invalid = ""
            model_chain = ["m"]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
                if call_verifier:
                    assert self.visible_verifier is not None
                    seen["verifier_stdout"] = self.visible_verifier(CANDIDATE, 0).stdout
                return CANDIDATE, {"source": "llm", "model_calls": 1, "model_name": "m"}

        return _Generator

    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    # The verifier is bound only through the executor's confined entry point (#2211); stand in
    # with the same in-place evaluation so hit and miss can be compared.
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    monkeypatch.setattr(
        sprint.InPlaceSprintExecutor,
        "evaluate_candidate_confined",
        sprint.InPlaceSprintExecutor.evaluate_candidate,
        raising=False,
    )
    # #2211: with NEXUS_CONFINE_VISIBLE_TEST=1 the executor itself confines its run (and
    # refuses without an OS barrier, e.g. Linux CI); this test compares memo hit vs miss of
    # the in-place evaluation, so it keeps the in-place path.
    monkeypatch.setattr(sprint, "_inplace_evaluate_confined", lambda *_a, **_k: None)
    outputs = {}
    for call_verifier in (True, False):
        monkeypatch.setattr(sprint, "LLMCandidateGenerator", make_generator(call_verifier))
        result = sprint.run_hyper_sprint(
            repo_root=tmp_path,
            config=sprint.SprintConfig(
                task="fix normalize",
                target_file="demo.py",
                test_file="test_demo.py",
                candidate_count=1,
                max_rounds=1,
                llm_mode=True,
            ),
        )
        llm = [c for c in result.candidates if c.candidate_code == CANDIDATE]
        assert llm, result.candidates
        outputs[call_verifier] = llm[0].stdout

    def normalise(text: str) -> str:
        return re.sub(r"in [0-9.]+s", "in Ns", text)

    assert normalise(outputs[True]) == normalise(outputs[False])
    assert normalise(seen["verifier_stdout"]) == normalise(outputs[True])
    assert "1 failed" in outputs[True]  # --maxfail=1, same as the sprint's own command


def test_no_verifier_status_is_not_success_in_the_real_runtime_callback(tmp_path: Path) -> None:
    """Codex #2212 F4a: UnifiedRuntime's own callback runner records the stage as FAILED."""

    from nexus_runtime.kernel import unified_runtime as kernel

    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-004"
    generator.visible_verifier_unbound_reason = "visible_test_confinement_unavailable"
    captured: dict[str, Any] = {}

    def ask_unified(request: Any, *, verifier: Any = None, **_kwargs: Any) -> dict[str, Any]:
        online = {
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"response": json.dumps(EDIT), "raw_response": ""},
        }
        captured["payload"] = dict(verifier({"task_id": request.task_id, "online": online}))
        return {"task_id": request.task_id, "online": online}

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    generator._ask_unified_candidate(
        prompt="p", payload="x", task="t", seed=1, attempt=1, model="m", source_code=SOURCE
    )
    payload = captured["payload"]
    assert payload["status"] == "no_verifier"
    assert payload["gate_passed"] is False
    assert payload["verifier_unbound_reason"] == "visible_test_confinement_unavailable"
    run_callback = next(
        value
        for value in vars(kernel.UnifiedRuntime).values()
        if getattr(getattr(value, "__func__", value), "__name__", "") == "_run_callback"
    )
    run_callback = getattr(run_callback, "__func__", run_callback)
    stage = run_callback(
        "verifier", lambda _ctx: payload, {"task_id": payload["task_id"]}, required=True
    )
    assert stage["status"] == "FAILED"
    assert stage["gate_passed"] is False


def test_sprint_binds_no_visible_verifier_without_confinement(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Codex #2212 F2 / Gemini G1+G11: the verifier executes model code only through the
    executor's ``evaluate_candidate_confined`` (with NEXUS_CONFINE_VISIBLE_TEST=1), never
    through plain ``evaluate_candidate``; without that method nothing is bound."""

    import nexus.research.sprint_service as sprint

    bound: dict[str, Any] = {}
    plain_calls: list[str] = []
    confined_calls: list[str] = []
    real_evaluate = sprint.InPlaceSprintExecutor.evaluate_candidate

    def plain_spy(self: Any, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        plain_calls.append(code)
        return real_evaluate(self, seed=seed, hint=hint, code=code, source=source)

    def confined_spy(self: Any, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        confined_calls.append(code)
        return CandidateEval(seed=seed, score=1.0, hint=hint, candidate_code=code, source=source)

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        visible_verifier_unbound_reason = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            bound["generator"] = self

        def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            if self.visible_verifier is not None:
                self.visible_verifier(CANDIDATE, 0)
            return CANDIDATE, {"source": "llm", "model_calls": 1, "model_name": "m"}

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setattr(sprint.InPlaceSprintExecutor, "evaluate_candidate", plain_spy)
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    (tmp_path / "demo.py").write_text(SOURCE)
    (tmp_path / "test_demo.py").write_text("def test_ok():\n    pass\n")

    def run() -> Any:
        bound.clear()
        plain_calls.clear()
        confined_calls.clear()
        sprint.run_hyper_sprint(
            repo_root=tmp_path,
            config=sprint.SprintConfig(
                task="fix normalize",
                target_file="demo.py",
                test_file="test_demo.py",
                candidate_count=1,
                max_rounds=1,
                llm_mode=True,
            ),
        )
        return bound["generator"]

    # 1. Env set, executor without evaluate_candidate_confined: unbound, verifier never ran.
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    # #2211 implements the method; remove it here to keep the "executor without it" case.
    monkeypatch.delattr(sprint.InPlaceSprintExecutor, "evaluate_candidate_confined", raising=False)
    assert not hasattr(sprint.InPlaceSprintExecutor, "evaluate_candidate_confined")
    generator = run()
    assert generator.visible_verifier is None
    assert generator.visible_verifier_unbound_reason == "visible_test_confinement_unavailable"
    assert confined_calls == []
    # Only the sprint's own (pre-existing) evaluation ran the candidate, once.
    assert plain_calls.count(CANDIDATE) == 1

    # 2. Method present but env unset: still unbound.
    monkeypatch.setattr(
        sprint.InPlaceSprintExecutor, "evaluate_candidate_confined", confined_spy, raising=False
    )
    monkeypatch.delenv("NEXUS_CONFINE_VISIBLE_TEST")
    generator = run()
    assert generator.visible_verifier is None
    assert confined_calls == []

    # 3. Method present and env set: the verifier calls the confined method, never the plain
    # one, and the sprint reuses that evaluation (memo), so plain never sees the candidate.
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    generator = run()
    assert generator.visible_verifier is not None
    assert confined_calls == [CANDIDATE]
    assert CANDIDATE not in plain_calls


def test_no_verifier_is_not_observed_by_the_runtime_replan_logic(tmp_path: Path) -> None:
    """Round 7: a no_verifier verdict is not a trusted verifier failure (no replan)."""

    from types import SimpleNamespace

    from nexus_runtime.kernel import unified_runtime as kernel
    from nexus_runtime.kernel.replan import build_execution_replan_request

    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-005"
    captured: dict[str, Any] = {}

    def ask_unified(request: Any, *, verifier: Any = None, **_kwargs: Any) -> dict[str, Any]:
        online = {
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"response": json.dumps(EDIT), "raw_response": ""},
        }
        captured["payload"] = dict(verifier({"task_id": request.task_id, "online": online}))
        return {"task_id": request.task_id, "online": online}

    generator.gateway.ask_unified = ask_unified  # type: ignore[method-assign]
    generator._ask_unified_candidate(
        prompt="p", payload="x", task="t", seed=1, attempt=1, model="m", source_code=SOURCE
    )
    payload = captured["payload"]
    assert payload["invoked"] is False
    assert payload["evidence_refs"] == []
    run_callback = next(
        value
        for value in vars(kernel.UnifiedRuntime).values()
        if getattr(getattr(value, "__func__", value), "__name__", "") == "_run_callback"
    )
    run_callback = getattr(run_callback, "__func__", run_callback)
    stage = run_callback(
        "verifier", lambda _ctx: payload, {"task_id": payload["task_id"]}, required=True
    )
    ctx = SimpleNamespace(
        EXECUTION_DEPTH_FULL="FULL", next_execution_depth_after_failure=lambda depth: "FULL"
    )
    request = build_execution_replan_request(
        ctx,  # type: ignore[arg-type]
        task_id=payload["task_id"],
        planner_decision_id="pd-1",
        current_execution_depth="LIGHT",
        verifier_stage=stage,
    )
    assert request["replan_required"] is False
    assert request["verifier_outcome_trusted"] is False
    assert request["trigger"] == "verifier_not_observed"

    # Gemini r2 N2: an undelivered payload and an edit that does not apply ran no test either.
    def raising_verifier(code: str, seed: int) -> CandidateEval:
        raise RuntimeError("evaluator crashed")

    def verdict_for(response_payload: Any, *, bind: bool, raises: bool = False) -> dict[str, Any]:
        gen = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
        gen._workspace_revision = lambda: "revision-verifier-006"
        if bind:
            gen.visible_verifier = lambda code, seed: CandidateEval(seed=seed, score=1.0)
        if raises:
            gen.visible_verifier = raising_verifier
        got: dict[str, Any] = {}

        def ask(request: Any, *, verifier: Any = None, **_kwargs: Any) -> dict[str, Any]:
            online = {"status": "SUCCEEDED", "invoked": True, "response": response_payload}
            got["payload"] = dict(verifier({"task_id": request.task_id, "online": online}))
            return {"task_id": request.task_id, "online": online}

        gen.gateway.ask_unified = ask  # type: ignore[method-assign]
        try:
            gen._ask_unified_candidate(
                prompt="p", payload="x", task="t", seed=1, attempt=1, model="m", source_code=SOURCE
            )
        except Exception:  # noqa: BLE001 - only the verifier verdict matters
            pass
        return got["payload"]

    unappliable = {**EDIT, "target_snippet": "not in source"}
    crashed = verdict_for(
        {"response": json.dumps(EDIT), "raw_response": ""}, bind=False, raises=True
    )
    # Round 9: an evaluator exception is "error", not a test failure.
    assert crashed["verifier_status"] == "error"
    assert crashed["visible_test_error"] == "visible_verifier_error:RuntimeError"
    assert "verifier_artifact" not in crashed
    for label, verdict in (
        ("verifier_raised", crashed),
        ("not_delivered", verdict_for({"response": "", "raw_response": ""}, bind=False)),
        (
            "edit_not_applied",
            verdict_for({"response": json.dumps(unappliable), "raw_response": ""}, bind=True),
        ),
    ):
        assert verdict["invoked"] is False, label
        assert verdict["evidence_refs"] == [], label
        assert verdict["status"] == "fail" and verdict.get("gate_passed") is False, label
        st = run_callback(
            "verifier", lambda _ctx, v=verdict: v, {"task_id": verdict["task_id"]}, required=True
        )
        req = build_execution_replan_request(
            ctx,  # type: ignore[arg-type]
            task_id=verdict["task_id"],
            planner_decision_id="pd-1",
            current_execution_depth="LIGHT",
            verifier_stage=st,
        )
        assert req["replan_required"] is False, label
        assert req["trigger"] == "verifier_not_observed", label

    # The old shape (invoked, candidate_response ref) was a trusted failure that replans.
    old = run_callback(
        "verifier",
        lambda _ctx: {
            **payload,
            "invoked": True,
            "evidence_refs": [f"verifier:{payload['task_id']}:candidate_response"],
        },
        {"task_id": payload["task_id"]},
        required=True,
    )
    old_request = build_execution_replan_request(
        ctx,  # type: ignore[arg-type]
        task_id=payload["task_id"],
        planner_decision_id="pd-1",
        current_execution_depth="LIGHT",
        verifier_stage=old,
    )
    assert old_request["replan_required"] is True


def test_structured_candidate_payload_is_whitelisted_and_status_comes_from_the_stage() -> None:
    """Gemini G9: a structured provider dict cannot forge status or smuggle extra keys."""

    from nexus.research.sprint_service import _candidate_out_from_online_stage

    forged = {
        "status": "APPROVED",
        "patch": "print('x')",
        "arbitrary_injection": "malicious",
        "tokens_used": 12,
    }
    failed = _candidate_out_from_online_stage({
        "status": "FAILED",
        "invoked": True,
        "response": {"response": forged},
    })
    assert failed["status"] == "FAIL"
    assert "arbitrary_injection" not in failed
    assert failed["patch"] == "print('x')" and failed["tokens_used"] == 12
    assert failed["candidate_response_path"] == "structured"
    ok = _candidate_out_from_online_stage({
        "status": "SUCCEEDED",
        "invoked": True,
        "response": {"response": {**forged, "status": "FAIL"}},
    })
    assert ok["status"] == "FAIL"  # tighten-only: the payload's own FAIL is kept
    assert (
        _candidate_out_from_online_stage({
            "status": "SUCCEEDED",
            "invoked": True,
            "response": {"response": forged},
        })["status"]
        == "APPROVED"
    )


def test_confined_contract_routes_every_sprint_evaluation_without_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Gemini r2 N1: with the contract active a memo miss (verifier never called) and every
    other sprint evaluation use evaluate_candidate_confined; plain is never called."""

    import nexus.research.sprint_service as sprint

    plain_calls: list[str] = []
    confined_calls: list[str] = []

    def plain_spy(self: Any, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        plain_calls.append(code)
        return CandidateEval(seed=seed, score=0.0, hint=hint, candidate_code=code, source=source)

    def confined_spy(self: Any, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        confined_calls.append(code)
        return CandidateEval(seed=seed, score=0.4, hint=hint, candidate_code=code, source=source)

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        visible_verifier_unbound_reason = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def generate(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
            # Never calls the verifier: every sprint evaluation is a memo miss.
            code = (
                CANDIDATE if kwargs.get("source_code") == SOURCE else kwargs["source_code"] + "#r"
            )
            return code, {"source": "llm", "model_calls": 1, "model_name": "m"}

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setattr(sprint.InPlaceSprintExecutor, "evaluate_candidate", plain_spy)
    monkeypatch.setattr(
        sprint.InPlaceSprintExecutor, "evaluate_candidate_confined", confined_spy, raising=False
    )
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    (tmp_path / "demo.py").write_text(SOURCE)
    (tmp_path / "test_demo.py").write_text("def test_ok():\n    pass\n")
    try:
        sprint.run_hyper_sprint(
            repo_root=tmp_path,
            config=sprint.SprintConfig(
                task="fix normalize",
                target_file="demo.py",
                test_file="test_demo.py",
                candidate_count=2,
                max_rounds=1,
                llm_mode=True,
            ),
        )
    except Exception:  # noqa: BLE001 - only which evaluator ran matters
        pass
    assert CANDIDATE in confined_calls
    assert plain_calls == []
