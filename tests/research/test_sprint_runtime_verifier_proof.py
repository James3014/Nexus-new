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
    for verdict in _gates(context).values():
        assert verdict["gate_passed"] is False
