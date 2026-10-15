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
    assert cmd[1:] == ["-m", "pytest", "-q", "--maxfail=1", "tests/test_visible.py"]


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
    # The verifier is bound only when the visible test runs confined (#2211); simulate that.
    monkeypatch.setattr(sprint, "visible_test_confinement_available", lambda: True)
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
    """Codex #2212 F2: without confinement the verifier executes no model code at all."""

    import nexus.research.sprint_service as sprint

    bound: dict[str, Any] = {}

    class _Generator:
        visible_verifier = None
        visible_test_target_invalid = ""
        visible_verifier_unbound_reason = ""
        model_chain = ["m"]

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            bound["generator"] = self

        def generate(self, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            raise sprint.LLMCandidateError("llm_no_patch", {"model_calls": 0})

    monkeypatch.setattr(sprint, "LLMCandidateGenerator", _Generator)
    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    (tmp_path / "demo.py").write_text(SOURCE)
    (tmp_path / "test_demo.py").write_text("def test_ok():\n    pass\n")
    # Env set but the confined runner module is absent on this tree: still unbound.
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    monkeypatch.setattr(sprint, "_CONFINED_TEST_RUNNER_MODULE", "nexus._absent_confined_runner")
    assert sprint.visible_test_confinement_available() is False
    monkeypatch.delenv("NEXUS_CONFINE_VISIBLE_TEST")
    assert sprint.visible_test_confinement_available() is False
    try:
        sprint.run_hyper_sprint(
            repo_root=tmp_path,
            config=sprint.SprintConfig(
                task="fix normalize",
                target_file="demo.py",
                test_file="test_demo.py",
                candidate_count=1,
                llm_mode=True,
            ),
        )
    except Exception:  # noqa: BLE001 - only the binding matters here
        pass
    generator = bound["generator"]
    assert generator.visible_verifier is None
    assert generator.visible_verifier_unbound_reason == "visible_test_confinement_unavailable"
    # Env + an importable confined runner module: available.
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    monkeypatch.setattr(sprint, "_CONFINED_TEST_RUNNER_MODULE", "nexus.research.sprint_service")
    assert sprint.visible_test_confinement_available() is True
