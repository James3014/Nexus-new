from __future__ import annotations

import io
import json

import pytest

from nexus.services.local_heal import lesson_embedding as le


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(le.EMBED_MODEL_ENV, raising=False)
    le._cache.clear()
    yield
    le._cache.clear()


def _fake_urlopen(calls, vector=(0.1, 0.2, 0.3)):
    def urlopen(request, timeout=None):
        calls.append((request, timeout))
        return io.BytesIO(json.dumps({"embedding": list(vector)}).encode())

    return urlopen


def test_returns_vector_and_posts_expected_payload(monkeypatch):
    calls: list = []
    monkeypatch.setattr(le, "_open", _fake_urlopen(calls))
    assert le.embed_text("x" * 5000) == [0.1, 0.2, 0.3]
    request, timeout = calls[0]
    assert timeout == 30
    assert request.full_url == "http://localhost:11434/api/embeddings"
    body = json.loads(request.data)
    assert body["model"] == "nomic-embed-text"
    assert len(body["prompt"]) == 4000


def test_none_on_urlopen_error(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("down")

    monkeypatch.setattr(le, "_open", boom)
    assert le.embed_text("hello") is None


def test_none_when_env_none(monkeypatch):
    calls: list = []
    monkeypatch.setattr(le, "_open", _fake_urlopen(calls))
    monkeypatch.setenv(le.EMBED_MODEL_ENV, "none")
    assert le.embed_text("hello") is None
    assert calls == []


def test_caches_repeats(monkeypatch):
    calls: list = []
    monkeypatch.setattr(le, "_open", _fake_urlopen(calls))
    assert le.embed_text("same") == le.embed_text("same")
    assert len(calls) == 1


def test_model_name_helper(monkeypatch):
    assert le.embed_model_name() == "nomic-embed-text"
    monkeypatch.setenv(le.EMBED_MODEL_ENV, "other-model")
    assert le.embed_model_name() == "other-model"
