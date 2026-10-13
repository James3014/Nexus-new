"""The S2T Ollama advisor never defaults to the retired 3b tag."""

from __future__ import annotations

import io
import json

import pytest
from nexus_runtime.planning.services import model_default_resolution as mdr

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2T3BAdvisor


def _candidates() -> list[S2TCandidate]:
    return [
        S2TCandidate(
            candidate_id="c1",
            source="test",
            content_ref="ref",
            selector_score=1.0,
            verifier_result="pass",
        )
    ]


def test_not_admitted_abstains_without_ollama_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_S2T_3B_OLLAMA_MODEL", raising=False)

    def _not_admitted(*_a, **_k):
        raise mdr.ModelDefaultNotAdmittedError("compact_diagnosis", "no_local_first_route")

    def _no_call(*_a, **_k):
        raise AssertionError("ollama must not be called without an admitted model")

    monkeypatch.setattr(mdr, "resolve_default_model", _not_admitted)
    monkeypatch.setattr("urllib.request.urlopen", _no_call)
    out = S2T3BAdvisor(force_simulation=True)._advise_via_ollama("low", _candidates())
    assert out["abstain_reason"].startswith("MODEL_DEFAULT_NOT_ADMITTED")


def test_default_model_comes_from_workforce_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_S2T_3B_OLLAMA_MODEL", raising=False)
    seen: dict[str, str] = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(req, timeout=0):
        seen["model"] = json.loads(req.data.decode("utf-8"))["model"]
        body = {"response": json.dumps({"selected_candidate_id": "c1"})}
        return _Resp(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(mdr, "resolve_default_model", lambda *_a, **_k: "admitted-model:9b")
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    out = S2T3BAdvisor(force_simulation=True)._advise_via_ollama("low", _candidates())
    assert seen["model"] == "admitted-model:9b"
    assert seen["model"] != "qwen2.5-s2t-advisor:3b"
    assert out["selected_candidate_id"] == "c1"
