"""#2721 L-B: VectorRAG creates and writes nothing under NEXUS_STATE_READ_ONLY=1."""

from __future__ import annotations

from nexus.core import vector_rag as vr


def _rag(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "lancedb", None)  # force the JSON fallback (the case that wrote files)
    monkeypatch.setattr(
        vr, "resolve_lancedb_root", lambda name, root: tmp_path / "state" / "vectors.lance"
    )
    return vr.VectorRAG()


def test_read_only_creates_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_STATE_READ_ONLY", "1")
    rag = _rag(tmp_path, monkeypatch)
    rag.update_index([{"task": "t", "solution": "s"}])
    assert not (tmp_path / "state").exists()
    assert rag._load_fallback_rows() == []


def test_without_switch_the_fallback_index_is_written(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_STATE_READ_ONLY", raising=False)
    rag = _rag(tmp_path, monkeypatch)
    rag.update_index([{"task": "t", "solution": "s"}])
    assert rag._load_fallback_rows() == [{"task": "t", "solution": "s"}]
    assert rag.fallback_file.exists()


def test_read_only_still_reads_an_existing_fallback_index(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_STATE_READ_ONLY", raising=False)
    _rag(tmp_path, monkeypatch).update_index([{"task": "t", "solution": "s"}])
    monkeypatch.setenv("NEXUS_STATE_READ_ONLY", "1")
    rag = _rag(tmp_path, monkeypatch)
    before = rag.fallback_file.read_bytes()
    rag.update_index([{"task": "u", "solution": "v"}])
    assert rag._load_fallback_rows() == [{"task": "t", "solution": "s"}]
    assert rag.fallback_file.read_bytes() == before
