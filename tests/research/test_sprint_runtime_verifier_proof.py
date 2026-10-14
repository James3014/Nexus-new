"""Wiring plan PR-1: the sprint's runtime verifier stage carries visible-test proof.

Before, the verifier stage only checked that an online payload existed, so the runtime
postflight artifact/claim/delivery gates blocked every row with
``missing_verifier_artifact`` / ``missing_verifier_source_hash``.  The verifier now applies the
online candidate, runs the sprint's visible-test evaluator (never the hidden test) and binds
the candidate sha256 and the sealed source hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from nexus.research.sprint_service import (
    BENCH_WORKFORCE_BINDINGS_ENV,
    CandidateEval,
    LLMCandidateGenerator,
)
from scripts.bench.agy_provider import AGY_DEFAULT_MODEL, configure_agy_lane_env

SOURCE = "def normalize(text):\n    return text\n"
CANDIDATE = "def normalize(text):\n    return text.strip()\n"
REPLY = json.dumps({
    "status": "APPROVED",
    "operation": "replace",
    "target_snippet": "return text",
    "replacement": "return text.strip()",
})
# The fake provider prints the edit payload itself, so the online stage's domain response is
# the edit the sprint applies.
FAKE_AGY = """#!{python}
print({reply!r})
"""
GATES = ("artifact_gate", "claim_gate", "delivery_gate")


def _lane_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "bin" / "agy"
    exe.parent.mkdir()
    exe.write_text(FAKE_AGY.format(python=sys.executable, reply=REPLY), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    env: dict[str, str] = {}
    configure_agy_lane_env(env)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert BENCH_WORKFORCE_BINDINGS_ENV in env
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    policy = tmp_path / ".nexus" / "online_execution_policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({"default_online_policy": "auto"}), encoding="utf-8")


def _ask(tmp_path: Path, *, visible_score: float) -> tuple[dict, list[str]]:
    seen: list[str] = []

    def visible(code: str, seed: int) -> CandidateEval:
        seen.append(code)
        return CandidateEval(seed=seed, score=visible_score, candidate_code=code)

    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-001"
    generator.visible_verifier = visible
    _out, _raw, receipt = generator._ask_unified_candidate(
        prompt="fix normalize",
        payload="Return one small edit.",
        task="fix normalize",
        seed=1,
        attempt=1,
        model=AGY_DEFAULT_MODEL,
        source_code=SOURCE,
    )
    return receipt, seen


def _verifier_response(receipt: dict) -> dict:
    verifier = receipt["verifier"]
    response = verifier.get("response")
    assert isinstance(response, dict)
    return response


def test_passing_visible_test_binds_candidate_sha_and_passes_postflight_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _lane_env(monkeypatch, tmp_path)
    receipt, seen = _ask(tmp_path, visible_score=1.0)

    assert seen == [CANDIDATE]  # the visible evaluator saw exactly the applied online candidate
    response = _verifier_response(receipt)
    sha = hashlib.sha256(CANDIDATE.encode("utf-8")).hexdigest()
    assert response["verifier_status"] == "pass"
    assert response["visible_test_passed"] is True
    assert response["verifier_artifact"] == f"sha256:{sha}"
    assert response["candidate_hash"] == sha
    bundle_source = receipt["capability_evidence_bundle"]["source_hash"]
    assert bundle_source and response["source_hash"] == bundle_source
    assert receipt["verifier"]["gate_passed"] is True
    results = receipt["capability_results"]
    assert set(GATES) <= set(results)
    for gate in GATES:
        if gate in results:
            refs = " ".join(results[gate]["evidence_refs"])
            assert "missing_verifier_artifact" not in refs
            assert "missing_verifier_source_hash" not in refs
            assert results[gate]["gate_passed"] is True, (gate, refs)


def test_failing_visible_test_fails_verifier_and_blocks_postflight_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _lane_env(monkeypatch, tmp_path)
    receipt, seen = _ask(tmp_path, visible_score=0.4)

    assert seen == [CANDIDATE]
    response = _verifier_response(receipt)
    assert response["verifier_status"] == "fail"
    assert response["visible_test_passed"] is False
    assert response["verifier_artifact"].startswith("sha256:")
    assert receipt["verifier"]["gate_passed"] is False
    results = receipt["capability_results"]
    assert set(GATES) <= set(results)
    for gate in GATES:
        if gate in results:
            refs = " ".join(results[gate]["evidence_refs"])
            assert results[gate]["gate_passed"] is False
            # Blocked by the real failing verdict, not by missing proof.
            assert "missing_verifier_artifact" not in refs
            assert "verifier_status_fail" in refs, (gate, refs)


def test_without_visible_evaluator_the_verifier_claims_no_test_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _lane_env(monkeypatch, tmp_path)
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-verifier-002"
    _out, _raw, receipt = generator._ask_unified_candidate(
        prompt="fix normalize",
        payload="Return one small edit.",
        task="fix normalize",
        seed=1,
        attempt=1,
        model=AGY_DEFAULT_MODEL,
        source_code=SOURCE,
    )
    response = _verifier_response(receipt)
    assert "verifier_status" not in response
    assert "verifier_artifact" not in response
